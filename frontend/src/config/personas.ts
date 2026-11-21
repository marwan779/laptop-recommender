import type { PersonaType } from '../types/api'

export type PersonaCategoryId = 'balanced' | 'daily' | 'tech' | 'gaming' | 'creative'

export interface PersonaSubOption {
  id: PersonaType
  labelAr: string
  labelEn: string
  hintAr: string
  hintEn: string
}

export interface PersonaCategoryDef {
  id: PersonaCategoryId
  defaultPersona: PersonaType
  labelAr: string
  labelEn: string
  descAr: string
  descEn: string
  subOptions: PersonaSubOption[]
}

export const PERSONA_CATEGORIES: PersonaCategoryDef[] = [
  {
    id: 'balanced',
    defaultPersona: 'balanced',
    labelAr: 'كل حاجة شوية',
    labelEn: 'Balanced',
    descAr: 'توازن بين السعر والأداء والاعتمادية',
    descEn: 'Balanced mix of price, speed and reliability',
    subOptions: [],
  },
  {
    id: 'daily',
    defaultPersona: 'daily_student',
    labelAr: 'دراسة وشغل ومكتب',
    labelEn: 'Study & Work',
    descAr: 'محاضرات، أوفيس، وتنقل يومي ببطارية طويلة',
    descEn: 'Study, office tasks and portable daily work',
    subOptions: [
      {
        id: 'daily_student',
        labelAr: 'دراسة وجامعة',
        labelEn: 'Study & University',
        hintAr: 'خفيف وسعر اقتصادي للمحاضرات والمذاكرة',
        hintEn: 'Value-focused for lectures and study',
      },
      {
        id: 'daily_business',
        labelAr: 'بيزنس وتنقل',
        labelEn: 'Business & Travel',
        hintAr: 'وزن خفيف جداً وبطارية تدوم طوال اليوم',
        hintEn: 'Ultralight build with all-day battery',
      },
      {
        id: 'daily_office',
        labelAr: 'أوفيس وإنتاجية',
        labelEn: 'Office & Productivity',
        hintAr: 'مريح للكتابة والاجتماعات وتعدد المهام',
        hintEn: 'Comfortable typing, webcam and multitasking',
      },
    ],
  },
  {
    id: 'tech',
    defaultPersona: 'tech',
    labelAr: 'برمجة وتقنية',
    labelEn: 'Tech & Dev',
    descAr: 'كود، ذكاء اصطناعي، وأنظمة وهمية',
    descEn: 'Coding, AI/ML, web dev and virtualization',
    subOptions: [
      {
        id: 'tech',
        labelAr: 'برمجة عامة',
        labelEn: 'General Tech',
        hintAr: 'توازن ممتاز للمعالج والرامات والشاشة',
        hintEn: 'All-round CPU, RAM and screen comfort',
      },
      {
        id: 'tech_web_mobile',
        labelAr: 'تطوير ويب وموبايل',
        labelEn: 'Web & Mobile Dev',
        hintAr: 'رامات كبيرة ومعالج سريع للكومبايل وDocker',
        hintEn: 'Fast compiles, Docker and smooth multitasking',
      },
      {
        id: 'tech_ai_ml',
        labelAr: 'ذكاء اصطناعي وبيانات',
        labelEn: 'AI / ML & Data',
        hintAr: 'كارت NVIDIA بذاكرة VRAM قوية لتدريب الموديلات',
        hintEn: 'NVIDIA CUDA + high VRAM for model training',
      },
      {
        id: 'tech_cyber_vms',
        labelAr: 'أمن سيبراني وVMs',
        labelEn: 'Cyber & VMs',
        hintAr: 'أنوية معالجة عالية وقابلية ترقية للرامات',
        hintEn: 'High core count and upgradeable RAM for VMs',
      },
    ],
  },
  {
    id: 'gaming',
    defaultPersona: 'gaming',
    labelAr: 'ألعاب',
    labelEn: 'Gaming',
    descAr: 'ألعاب حديثة بفريمات عالية وتبريد قوي',
    descEn: 'High-FPS gaming and dedicated graphics',
    subOptions: [
      {
        id: 'gaming',
        labelAr: 'ألعاب متوازن',
        labelEn: 'All-Round Gaming',
        hintAr: 'أفضل توازن بين الفريمات والتبريد والسعر',
        hintEn: 'Balanced FPS, thermals and value',
      },
      {
        id: 'gaming_esports',
        labelAr: 'ألعاب تنافسية (FPS)',
        labelEn: 'Esports (High Hz)',
        hintAr: 'شاشة سريعة 144Hz+ واستجابة عالية',
        hintEn: 'Fast 144Hz+ display for competitive play',
      },
      {
        id: 'gaming_aaa',
        labelAr: 'ألعاب ثقيلة (AAA)',
        labelEn: 'AAA & Ray Tracing',
        hintAr: 'أعلى كارت شاشة وVRAM وتبريد للألعاب الثقيلة',
        hintEn: 'Max GPU power & VRAM for heavy titles',
      },
      {
        id: 'gaming_budget',
        labelAr: 'ألعاب اقتصادي',
        labelEn: 'Budget Gaming',
        hintAr: 'أفضل أداء ألعاب ممكن بأقل سعر',
        hintEn: 'Best gaming value at an entry budget',
      },
    ],
  },
  {
    id: 'creative',
    defaultPersona: 'creative',
    labelAr: 'تصميم ومونتاج',
    labelEn: 'Creative',
    descAr: 'فوتوشوب، مونتاج فيديو، وتصميم 3D',
    descEn: 'Photo, video editing and 3D/CAD rendering',
    subOptions: [
      {
        id: 'creative',
        labelAr: 'إبداع عام',
        labelEn: 'General Creative',
        hintAr: 'شاشة دقيقة الألوان مع أداء رسومي متوازن',
        hintEn: 'Color-accurate screen with solid GPU',
      },
      {
        id: 'creative_video',
        labelAr: 'مونتاج فيديو',
        labelEn: 'Video Editing',
        hintAr: 'تصدير سريع ورامات عالية وشاشة دقيقة',
        hintEn: 'Fast timeline scrubbing, exports & color',
      },
      {
        id: 'creative_2d_photo',
        labelAr: 'تصميم جرافيك 2D',
        labelEn: '2D Photo & Design',
        hintAr: 'دقة ألوان عالية 100% sRGB وخفة في التنقل',
        hintEn: '100% sRGB / OLED accuracy for design',
      },
      {
        id: 'creative_3d_cad_gamedev',
        labelAr: 'تصميم 3D وهندسي',
        labelEn: '3D / CAD / Game Dev',
        hintAr: 'قوة جرافيكس ومعالجة وريندر مستقر',
        hintEn: 'Heavy 3D rendering, CAD and game engines',
      },
    ],
  },
]

export const PERSONA_LABELS: Record<PersonaType, { ar: string; en: string }> = {
  balanced: { ar: 'كل حاجة شوية', en: 'Balanced' },
  daily_student: { ar: 'دراسة وجامعة', en: 'Study & University' },
  daily_business: { ar: 'بيزنس وتنقل', en: 'Business & Travel' },
  daily_office: { ar: 'أوفيس وإنتاجية', en: 'Office & Productivity' },
  tech: { ar: 'برمجة عامة', en: 'General Tech' },
  tech_web_mobile: { ar: 'تطوير ويب وموبايل', en: 'Web & Mobile Dev' },
  tech_ai_ml: { ar: 'ذكاء اصطناعي وبيانات', en: 'AI / ML & Data' },
  tech_cyber_vms: { ar: 'أمن سيبراني وVMs', en: 'Cyber & VMs' },
  gaming: { ar: 'ألعاب متوازن', en: 'All-Round Gaming' },
  gaming_esports: { ar: 'ألعاب تنافسية (FPS)', en: 'Esports' },
  gaming_aaa: { ar: 'ألعاب ثقيلة (AAA)', en: 'AAA Gaming' },
  gaming_budget: { ar: 'ألعاب اقتصادي', en: 'Budget Gaming' },
  creative: { ar: 'إبداع عام', en: 'General Creative' },
  creative_video: { ar: 'مونتاج فيديو', en: 'Video Editing' },
  creative_2d_photo: { ar: 'تصميم جرافيك 2D', en: '2D Design' },
  creative_3d_cad_gamedev: { ar: 'تصميم 3D وهندسي', en: '3D / CAD / Game Dev' },
}

export const LEGACY_PERSONA_ALIASES: Record<string, PersonaType> = {
  ai_and_game_dev: 'tech_ai_ml',
  programming: 'tech_web_mobile',
  content_creation: 'creative',
  student_and_office: 'daily_student',
  business_and_mobility: 'daily_business',
}

export function resolvePersonaKey(raw: string | null | undefined): PersonaType {
  const key = (raw || '').toLowerCase().trim()
  if (key in LEGACY_PERSONA_ALIASES) {
    return LEGACY_PERSONA_ALIASES[key]
  }
  if (key in PERSONA_LABELS) {
    return key as PersonaType
  }
  return 'balanced'
}

export function findCategoryForPersona(persona: PersonaType): PersonaCategoryDef {
  for (const cat of PERSONA_CATEGORIES) {
    if (cat.defaultPersona === persona || cat.subOptions.some((s) => s.id === persona)) {
      return cat
    }
  }
  return PERSONA_CATEGORIES[0]
}
