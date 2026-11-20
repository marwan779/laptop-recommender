import React from 'react'
import { AlertTriangle, Cpu, Feather, Monitor, Wrench, Zap } from 'lucide-react'

export interface TierInfo {
  category: string
  title: string
  subtitle: string
  /** Tier key colour used only for the 2px left bar and the icon. */
  key: string
  icon: React.ReactNode
}

export function getSiliconTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo | null {
  const key = (raw || '').toUpperCase().trim()
  if (!key) return null

  if (key === 'HEAVILY_CAPPED_GPU') {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'شاسيه نحيف وقدرة جرافيكس مقيدة جداً (Capped TGP)' : 'Compact Chassis (Heavily Capped GPU)',
      subtitle: isAr ? 'تم تقييد استهلاك كارت الشاشة لتفادي الحرارة في هيكل نحيف، مما يقلل الأداء الأقصى' : 'GPU power significantly reduced for thin chassis cooling; lower peak FPS',
      key: 'var(--tier-thermal)',
      icon: <AlertTriangle className="w-4 h-4 text-[var(--warning)]" strokeWidth={1.8} />,
    }
  }
  if (key === 'MODERATELY_CAPPED_GPU') {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'قدرة جرافيكس معتدلة (Moderate TGP)' : 'Balanced Power (Moderate GPU TGP)',
      subtitle: isAr ? 'استهلاك كارت الشاشة مضبوط بشكل معتدل للموازنة بين الحرارة والهدوء والأداء' : 'GPU power tuned for balanced thermals & acoustic comfort',
      key: 'var(--tier-thermal)',
      icon: <Zap className="w-4 h-4 text-[var(--gold)]" strokeWidth={1.8} />,
    }
  }
  if (key === 'FULL_POWER_GPU' || key === 'DISCRETE_EXPLICIT_TGP' || (key.includes('HIGH') && !key.includes('CAPPED'))) {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'أداء كامل غير مقيد (Full Power TGP)' : 'High-Power Uncapped Chassis',
      subtitle: isAr ? 'تبريد قوي يسمح لكارت الشاشة بالعمل بكامل استهلاك الطاقة المصمم له' : 'Dedicated cooling allows max sustained GPU power',
      key: 'var(--tier-thermal)',
      icon: <Zap className="w-4 h-4 text-[var(--success)]" strokeWidth={1.8} />,
    }
  }
  if (key === 'INTEGRATED_SOC' || key.includes('INTEGRATED') || key.includes('SOC') || key.includes('ENTRY')) {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'معالجة موفرة واقتصادية (iGPU)' : 'Efficiency SoC (iGPU)',
      subtitle: isAr ? 'استهلاك طاقة منخفض وعمر بطارية أطول للدراسة والعمل اليومي' : 'Low power draw & extended battery life for daily work',
      key: 'var(--tier-thermal)',
      icon: <Cpu className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key === 'UNKNOWN_TGP_DGPU') {
    return {
      category: isAr ? 'فئة المعالجة والتبريد' : 'Thermal & Compute Tier',
      title: isAr ? 'كارت شاشة منفصل (TGP غير محدد)' : 'Discrete GPU (Standard Chassis)',
      subtitle: isAr ? 'كارت شاشة مخصص للألعاب والتصميم، قدرة الواط غير مصرحة رسمياً' : 'Dedicated graphics card; manufacturer unstated TGP wattage',
      key: 'var(--tier-thermal)',
      icon: <Zap className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return null
}

export function getDisplayTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo | null {
  const key = (raw || '').toLowerCase()
  if (!key) return null
  if (key.includes('100% srgb') || key.includes('creator') || key.includes('dci-p3') || key.includes('oled')) {
    return {
      category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
      title: isAr ? 'شاشة احترافية دقيقة الألوان (100% sRGB)' : 'Creator Accurate (100% sRGB)',
      subtitle: isAr ? 'تغطية لونية متكاملة ممتازة للتصميم والمونتاج وإنتاج المحتوى' : 'Vibrant color accuracy ideal for editing & media',
      key: 'var(--tier-display)',
      icon: <Monitor className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('45%') || key.includes('basic') || key.includes('ntsc')) {
    return {
      category: isAr ? 'فئة الشاشة والألوان' : 'Display Quality Tier',
      title: isAr ? 'شاشة قياسية للأعمال والدراسة (45% NTSC)' : 'Standard Display (45% NTSC)',
      subtitle: isAr ? 'ألوان قياسية مريحة مناسبة للبرمجة والقراءة والأوفيس' : 'Standard gamut suitable for code & office tasks',
      key: 'var(--tier-display)',
      icon: <Monitor className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return null
}

export function getPortabilityTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo | null {
  const key = (raw || '').toUpperCase()
  if (!key) return null
  if (key.includes('ULTRA') || key.includes('LIGHT')) {
    return {
      category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
      title: isAr ? 'خفيف جداً ونحيف للتنقل (< 1.6 كجم)' : 'Ultra-Portable (< 1.6kg)',
      subtitle: isAr ? 'تصميم فائق النحافة يسهل حمله في أي حقيبة طوال اليوم' : 'Ultra-slim chassis designed for effortless mobility',
      key: 'var(--tier-mobility)',
      icon: <Feather className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('DESKTOP') || key.includes('HEAVY')) {
    return {
      category: isAr ? 'التنقل والوزن' : 'Mobility & Weight Tier',
      title: isAr ? 'بديل مكتبي للأداء الثابت (> 2.4 كجم)' : 'Desktop Replacement (> 2.4kg)',
      subtitle: isAr ? 'شاسيه أثقل مصمم للثبات والتبريد العالي على المكتب' : 'Heavier chassis built for sustained gaming power',
      key: 'var(--tier-mobility)',
      icon: <Feather className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return null
}

export function getUpgradeabilityTierInfo(raw: string | undefined | null, isAr: boolean): TierInfo | null {
  const key = (raw || '').toUpperCase()
  if (!key) return null
  if (key.includes('MAXIMUM') || key.includes('HIGH') || key.includes('DUAL')) {
    return {
      category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
      title: isAr ? 'ترقية قصوى (فتحتان RAM + منفذان SSD)' : 'Dual RAM & Dual SSD Slots',
      subtitle: isAr ? 'سهولة تامة في مضاعفة الرامات وسعة التخزين مستقبلاً' : 'Full headroom to expand both memory & storage later',
      key: 'var(--tier-expansion)',
      icon: <Wrench className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  if (key.includes('LOCKED') || key.includes('SOLDERED')) {
    return {
      category: isAr ? 'قابلية الترقية المستقبلية' : 'Future Expansion Tier',
      title: isAr ? 'ذاكرة مدمجة غير قابلة للزيادة' : 'Soldered / Locked RAM',
      subtitle: isAr ? 'الرامات ملحومة باللوحة الأم، الترقية محصورة في وحدة التخزين' : 'Memory is soldered; expansion limited to SSD slot',
      key: 'var(--tier-expansion)',
      icon: <Wrench className="w-4 h-4" strokeWidth={1.8} />,
    }
  }
  return null
}
