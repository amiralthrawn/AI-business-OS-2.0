import { redirect } from "next/navigation";

// V2: contacts and channels now live in the Communications hub (brain/navigation_v2.md).
export default function ContactsPage() {
  redirect("/communications?tab=contacts");
}
