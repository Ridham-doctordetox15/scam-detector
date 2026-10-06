"use client";

import { cn } from "@/lib/utils";

const Bar = ({ className }: { className?: string }) => <div className={cn("shimmer rounded-md", className)} />;

/**
 * Placeholder shaped like the result card while a check runs. Hidden from assistive technology;
 * the status line ("Checking the message…") is what screen readers hear.
 */
export function ResultSkeleton() {
  return (
    <div aria-hidden="true" data-testid="result-skeleton" className="overflow-hidden rounded-2xl border bg-card shadow-soft">
      <div className="grid md:grid-cols-[17rem_1fr]">
        <div className="flex flex-col items-center gap-4 border-b bg-subtle p-6 md:border-b-0 md:border-r">
          <Bar className="h-3 w-16" />
          <div className="shimmer h-24 w-44 rounded-t-full" />
          <Bar className="h-6 w-32" />
          <Bar className="h-4 w-20" />
        </div>
        <div className="space-y-6 p-6">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-2.5">
              <Bar className="h-4 w-36" />
              <Bar className="h-3.5 w-full" />
              <Bar className="h-3.5 w-11/12" />
              <Bar className="h-3.5 w-3/4" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
