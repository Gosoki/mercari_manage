import { defineComponent, reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { authApi } from '@/api'
import { setLocale, SUPPORTED_LOCALES } from '@/i18n'

export default defineComponent({
  setup() {
    const router = useRouter()
    const formRef = ref()
    const loading = ref(false)
    const form = reactive({
      username: '',
      password: ''
    })
    const { t, locale } = useI18n()

    const localeOptions = computed(() => SUPPORTED_LOCALES.map(code => ({
      value: code,
      label: t(`lang.${code}`),
    })))

    function onLocaleChange(val) {
      setLocale(val)
    }

    const rules = computed(() => ({
      username: [{ required: true, message: t('login.usernameRequired'), trigger: 'blur' }],
      password: [{ required: true, message: t('login.passwordRequired'), trigger: 'blur' }]
    }))

    const handleLogin = async () => {
      await formRef.value?.validate()
      loading.value = true
      try {
        const res = await authApi.login(form)
        localStorage.setItem('auth_token', res.token)
        localStorage.setItem('auth_user', JSON.stringify(res.user))
        ElMessage.success(t('login.success'))
        router.replace('/dashboard')
      } finally {
        loading.value = false
      }
    }

    return {
      reactive,
      ref,
      computed,
      useRouter,
      ElMessage,
      useI18n,
      authApi,
      setLocale,
      SUPPORTED_LOCALES,
      router,
      formRef,
      loading,
      form,
      t,
      locale,
      localeOptions,
      onLocaleChange,
      rules,
      handleLogin,
    }
  },
})
