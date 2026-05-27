import { defineComponent, ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { transactionApi, warehouseApi } from '@/api/index.js'
import { warehouseShelfLabel } from '@/utils/warehouseLabel.js'
import { formatUnixSecLocal } from '@/utils/timeDisplay.js'

export default defineComponent({
  setup() {
    const { t } = useI18n()

    const list = ref([])
    const loading = ref(false)
    const warehouses = ref([])
    const total = ref(0)
    const page = ref(1)
    const pageSize = ref(20)
    const filters = ref({ type: '', warehouse_id: null })

    const typeConfig = computed(() => ({
      in: { label: t('system.txIn'), tag: 'success' },
      out: { label: t('system.txOut'), tag: 'danger' },
      transfer: { label: t('system.txTransfer'), tag: 'warning' }
    }))

    async function load() {
      loading.value = true
      const params = { page: page.value, page_size: pageSize.value }
      if (filters.value.type) params.type = filters.value.type
      if (filters.value.warehouse_id) params.warehouse_id = filters.value.warehouse_id
      const res = await transactionApi.list(params).finally(() => (loading.value = false))
      list.value = res.items
      total.value = res.total
    }

    function resetFilters() {
      filters.value = { type: '', warehouse_id: null }
      page.value = 1
      load()
    }

    onMounted(async () => {
      warehouses.value = await warehouseApi.list()
      load()
    })

    return {
      ref,
      onMounted,
      computed,
      useI18n,
      transactionApi,
      warehouseApi,
      warehouseShelfLabel,
      formatUnixSecLocal,
      t,
      list,
      loading,
      warehouses,
      total,
      page,
      pageSize,
      filters,
      typeConfig,
      load,
      resetFilters,
    }
  },
})
