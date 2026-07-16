import { computed, ref } from 'vue'

import { getErrorMessage, ragflowApi } from '../api/client'
import type { RagflowDataset, RagflowDocument } from '../types'

export const useRagflowKnowledge = () => {
  const datasets = ref<RagflowDataset[]>([])
  const documents = ref<RagflowDocument[]>([])
  const selectedDatasetId = ref('')
  const selectedFiles = ref<File[]>([])
  const loading = ref(false)
  const uploading = ref(false)
  const message = ref('')
  const error = ref('')
  const selectedDataset = computed(() => (
    datasets.value.find((dataset) => dataset.id === selectedDatasetId.value)
  ))

  const showMessage = (text: string, isError = false) => {
    message.value = isError ? '' : text
    error.value = isError ? text : ''
  }

  const fetchDocuments = async (datasetId = selectedDatasetId.value) => {
    if (!datasetId) {
      documents.value = []
      return
    }
    try {
      loading.value = true
      const data = await ragflowApi.documents(datasetId)
      if (data.error) {
        showMessage(data.error, true)
        documents.value = []
        return
      }
      documents.value = data.documents ?? []
    } catch (requestError) {
      showMessage(`获取知识库文档失败：${getErrorMessage(requestError)}`, true)
    } finally {
      loading.value = false
    }
  }

  const fetchDatasets = async () => {
    try {
      loading.value = true
      showMessage('')
      const data = await ragflowApi.datasets()
      if (data.error) {
        showMessage(data.error, true)
        datasets.value = []
        documents.value = []
        return
      }

      datasets.value = data.datasets ?? []
      const selectedExists = datasets.value.some(
        (dataset) => dataset.id === selectedDatasetId.value,
      )
      if (!selectedExists) selectedDatasetId.value = datasets.value[0]?.id ?? ''
      if (selectedDatasetId.value) await fetchDocuments(selectedDatasetId.value)
    } catch (requestError) {
      showMessage(`获取知识库列表失败：${getErrorMessage(requestError)}`, true)
    } finally {
      loading.value = false
    }
  }

  const selectDataset = async (dataset: RagflowDataset) => {
    selectedDatasetId.value = dataset.id
    await fetchDocuments(dataset.id)
  }

  const handleFileChange = (event: Event) => {
    const target = event.target as HTMLInputElement
    if (!target.files?.length) return
    selectedFiles.value = [...selectedFiles.value, ...Array.from(target.files)]
    target.value = ''
  }

  const uploadFiles = async () => {
    if (!selectedDatasetId.value || !selectedFiles.value.length) return
    try {
      uploading.value = true
      showMessage('')
      const names = selectedFiles.value.map((file) => file.name).join('、')
      const data = await ragflowApi.uploadDocuments(selectedDatasetId.value, selectedFiles.value)
      if (data.error) {
        showMessage(data.error, true)
        return
      }
      selectedFiles.value = []
      showMessage(`已上传并提交解析：${names}`)
      await fetchDatasets()
    } catch (requestError) {
      showMessage(`上传到 RAGFlow 失败：${getErrorMessage(requestError)}`, true)
    } finally {
      uploading.value = false
    }
  }

  const parseDocument = async (document: RagflowDocument) => {
    if (!selectedDatasetId.value) return
    try {
      showMessage('')
      const data = await ragflowApi.parseDocument(selectedDatasetId.value, document.id)
      if (data.error) {
        showMessage(data.error, true)
        return
      }
      showMessage(`已提交解析：${document.name}`)
      await fetchDocuments()
    } catch (requestError) {
      showMessage(`解析文档失败：${getErrorMessage(requestError)}`, true)
    }
  }

  const deleteDocument = async (document: RagflowDocument) => {
    if (!selectedDatasetId.value || !window.confirm(`确定删除文档“${document.name}”吗？`)) return
    try {
      showMessage('')
      const data = await ragflowApi.deleteDocument(selectedDatasetId.value, document.id)
      if (data.error) {
        showMessage(data.error, true)
        return
      }
      showMessage(`已删除文档：${document.name}`)
      await fetchDatasets()
    } catch (requestError) {
      showMessage(`删除文档失败：${getErrorMessage(requestError)}`, true)
    }
  }

  return {
    datasets,
    deleteDocument,
    documents,
    error,
    fetchDatasets,
    fetchDocuments,
    handleFileChange,
    loading,
    message,
    parseDocument,
    selectedDataset,
    selectedDatasetId,
    selectedFiles,
    selectDataset,
    uploading,
    uploadFiles,
  }
}
