import { cookies } from "next/headers";
import { setServerUserIdResolver, USER_COOKIE } from "@/lib/api";

// Server side of the profile header (see lib/api.ts): Server Components'
// API calls carry the profile selected in the browser. Imported once, for its
// side effect, by the root layout -- never by a Client Component.
setServerUserIdResolver(async () => (await cookies()).get(USER_COOKIE)?.value ?? null);
