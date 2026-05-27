import { defineComponent, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { categoryApi } from '@/api/index.js'

export default defineComponent({
  setup() {
    const { t } = useI18n()

    const list = ref([])
    const loading = ref(false)
    const dialogVisible = ref(false)
    const submitting = ref(false)
    const formRef = ref()
    const form = ref({ id: null, name: '', description: '' })
    const rules = { name: [{ required: true, message: t('system.categoryNameRequired'), trigger: 'blur' }] }

    async function load() {
      loading.value = true
      list.value = await categoryApi.list().finally(() => (loading.value = false))
    }

    function openDialog(row = null) {
      form.value = row ? { ...row } : { id: null, name: '', description: '' }
      dialogVisible.value = true
    }

    async function submit() {
      await formRef.value.validate()
      submitting.value = true
      try {
        if (form.value.id) await categoryApi.update(form.value.id, form.value)
        else await categoryApi.create(form.value)
        ElMessage.success(t('common.success'))
        dialogVisible.value = false
        load()
      } finally {
        submitting.value = false
      }
    }

    async function remove(id) {
      await categoryApi.remove(id)
      ElMessage.success(t('common.success'))
      load()
    }

    onMounted(load)

    return {
      ref,
      onMounted,
      ElMessage,
      useI18n,
      categoryApi,
      t,
      list,
      loading,
      dialogVisible,
      submitting,
      formRef,
      form,
      rules,
      load,
      openDialog,
      submit,
      remove,
    }
  },
})
