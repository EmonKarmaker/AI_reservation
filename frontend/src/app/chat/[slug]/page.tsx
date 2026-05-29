// Server component shell for /chat/[slug]. Awaits the dynamic params
// (Next.js 15+ Promise convention) and hands the slug to the client
// ChatWidget where all the interactive state lives.

import { ChatWidget } from "@/components/ChatWidget";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export default async function ChatPage({ params }: PageProps) {
  const { slug } = await params;
  return <ChatWidget slug={slug} />;
}
