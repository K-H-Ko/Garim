/*
코드 설명:
요금/크레딧 정책의 기본값과 포맷 유틸, 정책→플랜 변환 로직을 모은 모듈. usePricingPlans 훅은 관리자 정책을
불러와 기본값과 병합한 뒤 정렬된 구독/크레딧 플랜 목록을 제공한다.
*/
import { useEffect, useMemo, useState } from "react";
import { getAdminPolicySettings } from "../utils/api";

export const PLAN_KEYS = ["free", "pro", "studio"];

export const DEFAULT_POLICY = {
  file_processing: {
    plans: {
      free: {
        fileSizeLimit: 50,
        maxJobs: 3,
        monthlyQuota: 5,
        resultRetention: 0,
      },
      pro: {
        fileSizeLimit: 500,
        maxJobs: 10,
        monthlyQuota: 50,
        resultRetention: 7,
      },
      studio: {
        fileSizeLimit: 2048,
        maxJobs: 30,
        monthlyQuota: null,
        resultRetention: 14,
      },
    },
    allowedFormats: ["jpg", "jpeg", "png", "webp", "mp4", "mov"],
  },
  payment: {
    plans: {
      free: {
        credits: 10,
        price: 0,
        sortOrder: 10,
        status: "active",
      },
      pro: {
        credits: 60,
        price: 9900,
        sortOrder: 20,
        status: "active",
      },
      studio: {
        credits: 150,
        price: 19800,
        sortOrder: 30,
        status: "active",
      },
    },
    creditPlans: {
      credit_25: {
        name: "25 크레딧",
        credits: 25,
        bonusCredits: 0,
        price: 5000,
        sortOrder: 10,
        status: "active",
      },
      credit_80: {
        name: "80 크레딧",
        credits: 80,
        bonusCredits: 0,
        price: 15000,
        sortOrder: 20,
        status: "active",
      },
      credit_150: {
        name: "150 크레딧",
        credits: 150,
        bonusCredits: 0,
        price: 25000,
        sortOrder: 30,
        status: "active",
      },
    },
  },
  retention: {
    plans: {
      free: { autoDeleteOriginalHours: 12, metadataRetentionDays: 90 },
      pro: { autoDeleteOriginalHours: 12, metadataRetentionDays: 90 },
      studio: { autoDeleteOriginalHours: 12, metadataRetentionDays: 90 },
    },
  },
};

export const PLAN_META = {
  free: {
    name: "Free",
    badge: "Basic",
    badgeClass: "mui-chip--primary",
    description: "개인 진단과 가벼운 체험을 위한 무료 플랜.",
    cta: "무료로 시작",
  },
  pro: {
    name: "Pro",
    badge: "Most Popular",
    badgeClass: "mui-chip--soft-warning",
    featured: true,
    description: "정기적으로 영상을 다루는 크리에이터를 위한 플랜.",
    cta: "Pro 시작하기",
  },
  studio: {
    name: "Studio",
    badge: "Team",
    badgeClass: "mui-chip--secondary",
    description: "팀 단위 작업과 대량 분석을 위한 최상위 플랜.",
    cta: "Studio 시작하기",
  },
};

export function formatPrice(value) {
  const price = Number(value || 0);
  return price === 0 ? "0" : price.toLocaleString("ko-KR");
}

export function formatQuota(value, unit = "건") {
  if (value === null || value === undefined || value === "") return "무제한";
  return `${Number(value).toLocaleString("ko-KR")}${unit}`;
}

export function formatFileSize(value) {
  const size = Number(value || 0);
  if (size >= 1024) {
    return `${Number((size / 1024).toFixed(1)).toLocaleString("ko-KR")}GB`;
  }
  return `${size.toLocaleString("ko-KR")}MB`;
}

export function mergePolicy(base, incoming = {}) {
  const incomingFilePlans = incoming.file_processing?.plans;
  const incomingPaymentPlans = incoming.payment?.plans;
  const incomingRetentionPlans = incoming.retention?.plans;
  const incomingCreditPlans = incoming.payment?.creditPlans;

  return {
    file_processing: {
      ...base.file_processing,
      ...(incoming.file_processing || {}),
      plans: incomingFilePlans || base.file_processing.plans,
    },
    payment: {
      ...base.payment,
      ...(incoming.payment || {}),
      plans: incomingPaymentPlans || base.payment.plans,
      creditPlans: incomingCreditPlans || base.payment.creditPlans,
    },
    retention: {
      ...base.retention,
      ...(incoming.retention || {}),
      plans: incomingRetentionPlans || base.retention.plans,
    },
  };
}

export function buildPricingPlans(policy) {
  return Object.entries(policy.payment.plans || {})
    .map(([key, payment]) => {
      const meta = PLAN_META[key] || {
        name: payment.name || key,
        badge: "플랜",
        badgeClass: "mui-chip--primary",
        description: `${payment.name || key} 구독 플랜입니다.`,
        cta: Number(payment.price || 0) === 0 ? "무료로 시작" : "결제하기",
      };
      return {
        key,
        ...meta,
        name: payment.name || meta.name,
        badge: payment.badgeLabel || meta.badge,
        badgeClass: payment.badgeClass || meta.badgeClass,
        description: payment.description || meta.description,
        // 버튼 문구: 플랜 메타(cta)를 우선 사용, 없으면 price 기준 기본값
        cta: meta.cta || (Number(payment.price || 0) === 0 ? "무료로 시작" : "결제하기"),
        sortOrder: Number(payment.sortOrder ?? 0),
        status: payment.status || "active",
        file:
          policy.file_processing.plans[key] ||
          DEFAULT_POLICY.file_processing.plans[key] ||
          {},
        payment,
        retention:
          policy.retention.plans[key] ||
          DEFAULT_POLICY.retention.plans[key] ||
          {},
      };
    })
    .filter((plan) => plan.status === "active")
    .sort((a, b) => a.sortOrder - b.sortOrder);
}

export function buildCreditPlans(policy) {
  return Object.entries(policy.payment.creditPlans || {})
    .map(([key, credit]) => ({
      key,
      productType: "credit",
      name: credit.name || `${formatQuota(credit.credits, "개")} 크레딧`,
      sortOrder: Number(credit.sortOrder ?? 0),
      status: credit.status || "active",
      payment: {
        price: credit.price,
        credits: Number(credit.credits || 0) + Number(credit.bonusCredits || 0),
        baseCredits: credit.credits,
        bonusCredits: credit.bonusCredits || 0,
      },
      expiresDays: credit.expiresDays,
    }))
    .filter((plan) => plan.status === "active")
    .sort((a, b) => a.sortOrder - b.sortOrder);
}

export function usePricingPlans() {
  const [policy, setPolicy] = useState(DEFAULT_POLICY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function loadPolicy() {
      try {
        const response = await getAdminPolicySettings();
        if (cancelled) return;
        setPolicy(mergePolicy(DEFAULT_POLICY, response.data || {}));
      } catch (err) {
        console.error("Failed to load pricing policy", err);
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadPolicy();
    return () => {
      cancelled = true;
    };
  }, []);

  const plans = useMemo(() => buildPricingPlans(policy), [policy]);
  const creditPlans = useMemo(() => buildCreditPlans(policy), [policy]);

  return { plans, creditPlans, policy, loading, error };
}
