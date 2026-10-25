"use client";

import { useEffect } from "react";
import { grantFlowLoginPath } from "@/lib/auth-session";

export default function LoginPage() {
  useEffect(() => {
    window.location.replace(grantFlowLoginPath(new URLSearchParams(window.location.search).get('next')));
  }, []);

  return null;
}
