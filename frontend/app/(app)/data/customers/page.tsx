import { redirect } from "next/navigation";

// V2: the customers list lives in its workspace's sub-tab (brain/navigation_v2.md).
export default function ListPage() {
  redirect("/business/sales?tab=customers");
}
