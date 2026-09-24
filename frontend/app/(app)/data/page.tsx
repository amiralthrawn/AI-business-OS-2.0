import { redirect } from "next/navigation";

// V2: the former Data hub (4 widgets) is replaced by the workspaces --
// Catalogue (products, stock), Ventes > Clients, Achats > Fournisseurs,
// Finance > transactions (brain/navigation_v2.md).
export default function DataPage() {
  redirect("/data/products");
}
