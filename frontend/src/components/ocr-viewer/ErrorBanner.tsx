"use client";

import type { ApiError } from "@/lib/types";

interface ErrorBannerProps {
  error: ApiError;
}

export default function ErrorBanner({ error }: ErrorBannerProps) {
  return (
    <div className="error-banner" role="alert">
      <span className="error-code">{error.code}</span>
      <span className="error-message">{error.message}</span>
    </div>
  );
}
