import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { APPEARANCE_BOOTSTRAP_SCRIPT } from "@/lib/appearance";

export const metadata: Metadata = {
  title: "AI Signal Studio",
  description: "本地部署的 AI 信息工作台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{ __html: APPEARANCE_BOOTSTRAP_SCRIPT }}
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
