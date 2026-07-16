import type { RagflowImage, Message, MessageAttachment } from '../types'
import { apiClient } from '../api/client'

const IMAGE_TOKEN_PATTERN = /\{\{\s*image:([^}\s]+)\s*\}\}/gi

export const useImageAssets = () => {
  const objectUrls = new Map<string, string>()
  const metadataCache = new Map<string, RagflowImage>()

  const fetchContent = async (contentUrl: string): Promise<Blob> => {
    const response = await apiClient.get(contentUrl, { responseType: "blob" })
    return response.data as Blob
  }
  const attachmentCacheKey = (attachment: MessageAttachment) => (
    `attachment:${attachment.content_url}`
  )

  const rememberImageMetadata = (images: RagflowImage[]) => {
    for (const image of images) metadataCache.set(image.id, image)
  }

  const hydrateImageItem = async (image: RagflowImage): Promise<RagflowImage> => {
    const cachedUrl = objectUrls.get(image.id)
    if (cachedUrl) return { ...image, previewUrl: cachedUrl }

    try {
      const previewUrl = URL.createObjectURL(await fetchContent(image.content_url))
      objectUrls.set(image.id, previewUrl)
      return { ...image, previewUrl }
    } catch (error) {
      console.error(`加载图片预览失败：${image.filename}`, error)
      return image
    }
  }

  const hydrateImageItems = (images: RagflowImage[]) => (
    Promise.all(images.map(hydrateImageItem))
  )

  const referencedImageIds = (content: string) => {
    const ids: string[] = []
    for (const match of content.matchAll(IMAGE_TOKEN_PATTERN)) {
      const imageId = match[1]
      if (imageId && !ids.includes(imageId)) ids.push(imageId)
    }
    return ids
  }

  const resolveReferencedImages = async (messages: Message[]) => {
    for (const message of messages) rememberImageMetadata(message.images ?? [])


    for (const message of messages) {
      const images = [...(message.images ?? [])]
      const attachedIds = new Set(images.map((image) => image.id))
      for (const imageId of referencedImageIds(message.content)) {
        const image = metadataCache.get(imageId)
        if (image && !attachedIds.has(imageId)) {
          images.push(image)
          attachedIds.add(imageId)
        }
      }
      message.images = images
    }
  }

  const hydrateAttachmentItem = async (
    attachment: MessageAttachment,
  ): Promise<MessageAttachment> => {
    if (!attachment.content_type.startsWith('image/') || !attachment.content_url.startsWith('/api/')) {
      return attachment
    }
    const cacheKey = attachmentCacheKey(attachment)
    const cachedUrl = objectUrls.get(cacheKey)
    if (cachedUrl) return { ...attachment, previewUrl: cachedUrl }

    try {
      const previewUrl = URL.createObjectURL(
        await fetchContent(attachment.content_url),
      )
      objectUrls.set(cacheKey, previewUrl)
      return { ...attachment, previewUrl }
    } catch (error) {
      console.error(`加载附件预览失败：${attachment.name}`, error)
      return attachment
    }
  }

  const hydrateMessages = async (messages: Message[]) => {
    await resolveReferencedImages(messages)
    await Promise.all(messages.map(async (message) => {
      if (message.images?.length) message.images = await hydrateImageItems(message.images)
      if (message.attachments?.length) {
        message.attachments = await Promise.all(message.attachments.map(hydrateAttachmentItem))
      }
    }))
  }

  const createPendingAttachments = (files: File[]): MessageAttachment[] => files.map((file) => {
    const attachment: MessageAttachment = {
      name: file.name,
      content_type: file.type || 'application/octet-stream',
      size: file.size,
      content_url: `pending:${crypto.randomUUID()}`,
    }
    if (file.type.startsWith('image/')) {
      const previewUrl = URL.createObjectURL(file)
      objectUrls.set(attachmentCacheKey(attachment), previewUrl)
      attachment.previewUrl = previewUrl
    }
    return attachment
  })

  const adoptAttachmentPreview = (
    pending: MessageAttachment | undefined,
    attachment: MessageAttachment,
  ) => {
    if (!pending?.previewUrl) return
    objectUrls.delete(attachmentCacheKey(pending))
    objectUrls.set(attachmentCacheKey(attachment), pending.previewUrl)
    attachment.previewUrl = pending.previewUrl
  }

  const forgetImage = (imageId: string) => {
    const previewUrl = objectUrls.get(imageId)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    objectUrls.delete(imageId)
    metadataCache.delete(imageId)
  }

  const release = () => {
    for (const url of objectUrls.values()) URL.revokeObjectURL(url)
    objectUrls.clear()
    metadataCache.clear()
  }

  return {
    adoptAttachmentPreview,
    createPendingAttachments,
    forgetImage,
    hydrateImageItems,
    hydrateMessages,
    release,
    rememberImageMetadata,
    resolveReferencedImages,
  }
}
