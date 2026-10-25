"use client";
import { motion } from "framer-motion";
import { LucideIcon } from "lucide-react";
import { clsx } from "clsx";

interface StatCardProps {
  label: string;
  value: number | string;
  icon: LucideIcon;
  color?: string;
  loading?: boolean;
  delay?: number;
}

export function StatCard({ label, value, icon: Icon, color = "#6366f1", loading, delay = 0 }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="glass p-4 rounded-xl flex flex-col gap-2"
    >
      <div className="flex items-center justify-between">
        <span className="text-zinc-400 text-xs font-medium uppercase tracking-wide">{label}</span>
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{ background: `${color}20` }}
        >
          <Icon className="w-3.5 h-3.5" style={{ color }} />
        </div>
      </div>
      {loading ? (
        <div className="h-7 w-16 bg-zinc-700 animate-pulse rounded" />
      ) : (
        <span className="text-2xl font-bold text-zinc-100">{value}</span>
      )}
    </motion.div>
  );
}
