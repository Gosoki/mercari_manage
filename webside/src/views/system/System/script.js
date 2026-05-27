import { defineComponent, reactive, ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshRight } from '@element-plus/icons-vue'
import { authApi, configApi, mercariAccountApi, systemApi } from '@/api/index.js'
import {
  MERCARI_AREAS,
  JP_REGION_OPTIONS,
  getRegionIdForAreaId,
  normalizeShippingFromSeed
} from '@/constants/mercariJapanAreas.js'

export default defineComponent({
  setup() {
    const { t } = useI18n()

    const SHIPPING_FROM_AREA_PREFIX = 'AREA:'
    const SHIPPING_FROM_REGION_PREFIX = 'REGION:'

    const shippingFromCascaderProps = {
      value: 'value',
      label: 'label',
      children: 'children',
      emitPath: true,
      checkStrictly: false
    }

    const shippingFromCascaderOptions = computed(() =>
      JP_REGION_OPTIONS.map((r) => ({
        value: `${SHIPPING_FROM_REGION_PREFIX}${r.id}`,
        label: r.label,
        children: r.areaIds
          .map((aid) => {
            const a = MERCARI_AREAS.find((x) => x.id === aid)
            return a ? { value: `${SHIPPING_FROM_AREA_PREFIX}${a.id}`, label: a.name } : null
          })
          .filter(Boolean)
      }))
    )

    const shippingPayerOptions = computed(() => [
      { label: t('system.shippingPayerSeller'), value: 'seller' },
      { label: t('system.shippingPayerBuyer'), value: 'buyer' }
    ])
    const shippingMethodOptions = computed(() => [
      { label: t('system.shippingMethodUndecided'), value: 'undecided' },
      { label: 'らくらくメルカリ便', value: 'rakuraku' },
      { label: 'ゆうゆうメルカリ便', value: 'yuuyu' },
      { label: t('system.shippingMethodRegularMail'), value: 'regular_mail' }
    ])
    const shippingDaysOptions = computed(() => [
      { label: t('system.shippingDays12'), value: '1_2_days' },
      { label: t('system.shippingDays23'), value: '2_3_days' },
      { label: t('system.shippingDays47'), value: '4_7_days' }
    ])
    // 自动出品兜底默认：商品状态 / 售卖类型
    const conditionOptions = computed(() => [
      { label: t('system.conditionNewUnused'), value: 'new_unused' },
      { label: t('system.conditionAlmostUnused'), value: 'almost_unused' },
      { label: t('system.conditionGood'), value: 'good' },
      { label: t('system.conditionFair'), value: 'fair' },
      { label: t('system.conditionUsed'), value: 'used' }
    ])
    const saleTypeOptions = computed(() => [
      { label: t('system.saleTypeInstantBuy'), value: 'instant_buy' },
      { label: t('system.saleTypeAuction'), value: 'auction' }
    ])

    function buildShippingFromPath(areaId) {
      if (!areaId) return []
      const regionId = getRegionIdForAreaId(areaId)
      if (!regionId) return []
      return [`${SHIPPING_FROM_REGION_PREFIX}${regionId}`, `${SHIPPING_FROM_AREA_PREFIX}${areaId}`]
    }

    function mercariAccountOptionLabel(a) {
      const name = (a?.account_name || '').trim() || `ID ${a?.id}`
      const sid = String(a?.seller_id || '').trim()
      const tail = sid ? ` · ${t('system.seller')} ${sid}` : ''
      const inactive = a?.status === 'disabled' ? `（${t('system.inactive')}）` : ''
      return `${name}${tail}${inactive}`
    }

    const listingDefForm = reactive({
      shipping_from_path: [],
      shipping_method: null,
      shipping_payer: null,
      shipping_days: null,
      mercari_account_id: null,
      // 自动出品兜底默认（库存不存这两个字段）
      condition: null,
      sale_type: null
    })

    const listingDefLoading = ref(false)
    const listingDefSaving = ref(false)
    const mercariAccountOptions = ref([])
    const mercariAccountsLoading = ref(false)

    function onShippingFromChange(path) {
      const picked = Array.isArray(path) ? path[path.length - 1] : null
      if (!picked || !String(picked).startsWith(SHIPPING_FROM_AREA_PREFIX)) {
        listingDefForm.shipping_from_path = []
      }
    }

    async function fetchMercariAccounts() {
      mercariAccountsLoading.value = true
      try {
        const res = await mercariAccountApi.list({ page: 1, page_size: 500 })
        mercariAccountOptions.value = Array.isArray(res?.items) ? res.items : []
      } catch {
        mercariAccountOptions.value = []
      } finally {
        mercariAccountsLoading.value = false
      }
    }

    function pathToAreaId(path) {
      const picked = Array.isArray(path) ? path[path.length - 1] : null
      if (!picked || !String(picked).startsWith(SHIPPING_FROM_AREA_PREFIX)) return null
      const id = String(picked).slice(SHIPPING_FROM_AREA_PREFIX.length).trim()
      return id || null
    }

    async function loadListingDefaults() {
      listingDefLoading.value = true
      try {
        await fetchMercariAccounts()
        const d = await configApi.getListingDefaults()
        const area = normalizeShippingFromSeed(d?.shipping_from_area_id)
        listingDefForm.shipping_from_path = buildShippingFromPath(area)
        listingDefForm.shipping_method = d?.shipping_method ?? null
        listingDefForm.shipping_payer = d?.shipping_payer ?? null
        listingDefForm.shipping_days = d?.shipping_days ?? null
        listingDefForm.condition = d?.condition ?? null
        listingDefForm.sale_type = d?.sale_type ?? null
        listingDefForm.mercari_account_id =
          d?.mercari_account_id != null && Number.isFinite(Number(d.mercari_account_id)) && Number(d.mercari_account_id) > 0
            ? Number(d.mercari_account_id)
            : null
      } catch {
        /* 拦截器已提示 */
      } finally {
        listingDefLoading.value = false
      }
    }

    async function saveListingDefaults() {
      listingDefSaving.value = true
      try {
        const areaId = pathToAreaId(listingDefForm.shipping_from_path)
        await configApi.putListingDefaults({
          shipping_from_area_id: areaId,
          shipping_method: listingDefForm.shipping_method,
          shipping_payer: listingDefForm.shipping_payer,
          shipping_days: listingDefForm.shipping_days,
          condition: listingDefForm.condition,
          sale_type: listingDefForm.sale_type,
          mercari_account_id: listingDefForm.mercari_account_id
        })
        ElMessage.success(t('system.listingDefaultsSaved'))
        await loadListingDefaults()
      } catch {
        /* 拦截器 */
      } finally {
        listingDefSaving.value = false
      }
    }

    const users = ref([])
    const loading = ref(false)
    const restarting = ref(false)

    async function confirmRestartSystem() {
      try {
        await ElMessageBox.confirm(
          t('system.restartConfirmMsg'),
          t('system.restartSystem'),
          { type: 'warning', confirmButtonText: t('system.confirmRestart'), cancelButtonText: t('common.cancel') }
        )
      } catch {
        return
      }
      restarting.value = true
      try {
        const res = await systemApi.restart()
        ElMessage.success(res?.message || t('system.restartingMsg'))
      } catch {
        /* 拦截器已提示；进程退出时也可能出现网络错误，仍提示用户稍后刷新 */
      } finally {
        restarting.value = false
      }
    }

    const userDialogVisible = ref(false)
    const userSubmitting = ref(false)
    const userFormRef = ref()
    const userForm = reactive({
      username: '',
      display_name: '',
      password: ''
    })
    const userRules = {
      username: [{ required: true, message: t('login.usernameRequired'), trigger: 'blur' }],
      password: [{ required: true, message: t('login.passwordRequired'), trigger: 'blur' }, { min: 6, message: t('system.passwordMin6'), trigger: 'blur' }]
    }

    const pwdSubmitting = ref(false)
    const pwdFormRef = ref()
    const pwdForm = reactive({
      old_password: '',
      new_password: '',
      confirm_password: ''
    })
    const pwdRules = {
      old_password: [{ required: true, message: t('system.oldPasswordRequired'), trigger: 'blur' }],
      new_password: [{ required: true, message: t('system.newPasswordRequired'), trigger: 'blur' }, { min: 6, message: t('system.newPasswordMin6'), trigger: 'blur' }],
      confirm_password: [
        { required: true, message: t('system.confirmPasswordRequired'), trigger: 'blur' },
        {
          validator: (rule, value, callback) => {
            if (value !== pwdForm.new_password) callback(new Error(t('validation.passwordMismatch')))
            else callback()
          },
          trigger: 'blur'
        }
      ]
    }

    async function loadUsers() {
      loading.value = true
      try {
        users.value = await authApi.listUsers()
      } finally {
        loading.value = false
      }
    }

    function openUserDialog() {
      userForm.username = ''
      userForm.display_name = ''
      userForm.password = ''
      userDialogVisible.value = true
    }

    async function submitUser() {
      await userFormRef.value.validate()
      userSubmitting.value = true
      try {
        await authApi.createUser(userForm)
        ElMessage.success(t('system.userCreatedSuccess'))
        userDialogVisible.value = false
        await loadUsers()
      } finally {
        userSubmitting.value = false
      }
    }

    async function submitPassword() {
      await pwdFormRef.value.validate()
      pwdSubmitting.value = true
      try {
        await authApi.changePassword({
          old_password: pwdForm.old_password,
          new_password: pwdForm.new_password
        })
        ElMessage.success(t('system.passwordChangedSuccess'))
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_user')
        window.location.hash = '#/login'
      } finally {
        pwdSubmitting.value = false
      }
    }

    onMounted(async () => {
      await Promise.all([loadUsers(), loadListingDefaults()])
    })

    return {
      reactive,
      ref,
      onMounted,
      computed,
      useI18n,
      ElMessage,
      ElMessageBox,
      Plus,
      RefreshRight,
      authApi,
      configApi,
      mercariAccountApi,
      systemApi,
      MERCARI_AREAS,
      JP_REGION_OPTIONS,
      getRegionIdForAreaId,
      normalizeShippingFromSeed,
      t,
      SHIPPING_FROM_AREA_PREFIX,
      SHIPPING_FROM_REGION_PREFIX,
      shippingFromCascaderProps,
      shippingFromCascaderOptions,
      shippingPayerOptions,
      shippingMethodOptions,
      shippingDaysOptions,
      conditionOptions,
      saleTypeOptions,
      buildShippingFromPath,
      mercariAccountOptionLabel,
      listingDefForm,
      listingDefLoading,
      listingDefSaving,
      mercariAccountOptions,
      mercariAccountsLoading,
      onShippingFromChange,
      fetchMercariAccounts,
      pathToAreaId,
      loadListingDefaults,
      saveListingDefaults,
      users,
      loading,
      restarting,
      confirmRestartSystem,
      userDialogVisible,
      userSubmitting,
      userFormRef,
      userForm,
      userRules,
      pwdSubmitting,
      pwdFormRef,
      pwdForm,
      pwdRules,
      loadUsers,
      openUserDialog,
      submitUser,
      submitPassword,
    }
  },
})
