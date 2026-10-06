import type { Metadata } from "next";
import { AboutContent } from "@/components/AboutContent";
import { en } from "@/i18n/en";

export const metadata: Metadata = { title: `${en.about.title} - ${en.meta.title}` };

export default function AboutPage() {
  return <AboutContent />;
}
