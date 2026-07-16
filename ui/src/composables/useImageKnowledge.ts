import { ref } from 'vue'

import { getErrorMessage, imageKnowledgeApi } from '../api/client'
import type { ImageKnowledgeItem } from '../types'

interface ImageAssetManager {
  forgetImage: (imageId: string) => void
  hydrateImageItems: (images: ImageKnowledgeItem[]) => Promise<ImageKnowledgeItem[]>
  rememberImageMetadata: (images: ImageKnowledgeItem[]) => void
}

export const useImageKnowledge = (assets: ImageAssetManager) => {
  const items = ref<ImageKnowledgeItem[]>([])
  const selectedFiles = ref<File[]>([])
  const description = ref('')
  const loading = ref(false)
  const uploading = ref(false)
  const message = ref('')
  const error = ref('')

  const showMessage = (text: string, isError = false) => {
    message.value = isError ? '' : text
    error.value = isError ? text : ''
  }

  const fetchImages = async () => {
    try {
      loading.value = true
      showMessage('')
      const data = await imageKnowledgeApi.list()
      const images = (data.images ?? []) as ImageKnowledgeItem[]
      assets.rememberImageMetadata(images)
      items.value = await assets.hydrateImageItems(images)
    } catch (requestError) {
      showMessage(`读取图片知识库失败：${getErrorMessage(requestError)}`, true)
    } finally {
      loading.value = false
    }
  }

  const handleFileChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    if (!target.files?.length) return
    selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
    target.value = ''
  }

  const uploadImages = async () => {
    if (!selectedFiles.value.length) return
    try {
      uploading.value = true
      showMessage('')
      const data = await imageKnowledgeApi.upload(selectedFiles.value, description.value)
      const count = data.images?.length ?? 0
      selectedFiles.value = []
      description.value = ''
      showMessage(`已完成 ${count} 张图片的向量化和入库`)
      await fetchImages()
    } catch (requestError) {
      showMessage(`图片入库失败：${getErrorMessage(requestError)}`, true)
    } finally {
      uploading.value = false
    }
  }

  const deleteImage = async (image: ImageKnowledgeItem) => {
    if (!window.confirm(`确定从图片知识库删除“${image.filename}”吗？`)) return
    try {
      await imageKnowledgeApi.remove(image.id)
      assets.forgetImage(image.id)
      showMessage(`已删除图片：${image.filename}`)
      await fetchImages()
    } catch (requestError) {
      showMessage(`删除图片失败：${getErrorMessage(requestError)}`, true)
    }
  }

  return {
    deleteImage,
    description,
    error,
    fetchImages,
    handleFileChange,
    items,
    loading,
    message,
    selectedFiles,
    uploading,
    uploadImages,
  }
}
