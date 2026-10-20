/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LYSSTACK_API_URL?: string;
  readonly VITE_LYSCONTROL_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
