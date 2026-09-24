"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { createUser, updateUser } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/objects";
import type { AccessCatalog, Role, RoleRead, UserProfileRead } from "@/lib/types";

// Profiles, roles and custom access (V2.1, brain/permissions.md).
// ROLE -> default permissions, + what a director grants, - what they revoke.
// The backend enforces the result; this screen only edits it. Nobody edits
// their own access (the backend refuses it too).
export default function UsersAndRoles({
  users,
  roles,
  catalog,
  canManage,
  selfId,
}: {
  users: UserProfileRead[];
  roles: RoleRead[];
  catalog: AccessCatalog | null;
  canManage: boolean;
  selfId: string | null;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("sales");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  function toggle(u: UserProfileRead, permission: string, on: boolean) {
    const defaults = new Set(catalog?.role_defaults[u.role] ?? []);
    const grants = new Set(u.access_grants);
    const revokes = new Set(u.access_revokes);
    grants.delete(permission);
    revokes.delete(permission);
    if (on && !defaults.has(permission)) grants.add(permission);
    if (!on && defaults.has(permission)) revokes.add(permission);
    run(() => updateUser(u.id, { access_grants: [...grants], access_revokes: [...revokes] } as never));
  }

  const groups = catalog ? [...new Set(catalog.items.map((i) => i.group))] : [];

  return (
    <div className="space-y-5">
      <Card className="divide-y divide-border">
        {users.length === 0 && <p className="p-5 text-[13px] text-text-faint">Aucun profil. Sans profil sélectionné, l&rsquo;application fonctionne en accès complet (mode opérateur unique).</p>}
        {users.map((u) => {
          const isSelf = u.id === selfId;
          const editable = canManage && !isSelf;
          const defaults = new Set(catalog?.role_defaults[u.role] ?? []);
          const custom = u.access_grants.length + u.access_revokes.length;
          return (
            <div key={u.id} className="p-4 text-[13.5px]">
              <div className="flex flex-wrap items-center gap-3">
                <span className="flex-1 font-medium text-text">
                  {u.name} {isSelf && <span className="text-[12px] font-normal text-text-faint">(vous)</span>}
                </span>
                {!u.is_active && <Badge label="Désactivé" tone="neutral" />}
                {custom > 0 && <Badge label={`Accès personnalisés (${custom})`} tone="accent" />}
                {editable ? (
                  <select value={u.role} disabled={busy} onChange={(e) => run(() => updateUser(u.id, { role: e.target.value as Role }))} className="rounded-lg border-[1.5px] border-border-strong px-2 py-1.5 text-[13px] outline-none focus:border-accent">
                    {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
                  </select>
                ) : (
                  <Badge label={ROLE_LABEL[u.role]} tone="accent" />
                )}
                {catalog && (
                  <button type="button" onClick={() => setOpen(open === u.id ? null : u.id)} className="text-[12.5px] font-medium text-accent-strong hover:underline">
                    {open === u.id ? "Fermer" : editable ? "Gérer les accès" : "Voir les accès"}
                  </button>
                )}
                {editable && (
                  <button type="button" disabled={busy} onClick={() => run(() => updateUser(u.id, { is_active: !u.is_active }))} className="text-[12.5px] text-text-faint hover:text-text">
                    {u.is_active ? "Désactiver" : "Réactiver"}
                  </button>
                )}
              </div>
              {open === u.id && catalog && (
                <div className="mt-4 grid gap-5 md:grid-cols-2">
                  {groups.map((group) => (
                    <div key={group}>
                      <p className="mb-2 text-[11.5px] font-bold uppercase tracking-wide text-text-faint">{group}</p>
                      <ul className="space-y-1.5">
                        {catalog.items.filter((i) => i.group === group).map((item) => {
                          const on = u.permissions.includes(item.permission);
                          const changed = on !== defaults.has(item.permission);
                          return (
                            <li key={item.permission}>
                              <label className={`flex items-center gap-2.5 text-[13px] ${editable ? "cursor-pointer" : ""}`}>
                                <input type="checkbox" checked={on} disabled={!editable || busy} onChange={(e) => toggle(u, item.permission, e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
                                <span className={on ? "text-text" : "text-text-faint"}>{item.label}</span>
                                {item.sensitive && <Badge label="Sensible" tone="warning" />}
                                {changed && <span className="text-[11px] text-accent-strong">{on ? "ajouté par la direction" : "retiré par la direction"}</span>}
                              </label>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                  {isSelf && <p className="text-[12px] text-text-faint md:col-span-2">Vous ne pouvez pas modifier vos propres accès : un autre profil Direction doit le faire.</p>}
                </div>
              )}
            </div>
          );
        })}
      </Card>

      {canManage && (
        <div className="flex flex-wrap items-center gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nom de la personne" className="rounded-xl border-[1.5px] border-border-strong px-4 py-2.5 text-[13.5px] outline-none focus:border-accent" />
          <select value={role} onChange={(e) => setRole(e.target.value as Role)} className="rounded-xl border-[1.5px] border-border-strong px-3 py-2.5 text-[13.5px] outline-none focus:border-accent">
            {roles.map((r) => <option key={r.role} value={r.role}>{r.label}</option>)}
          </select>
          <Button disabled={!name.trim()} loading={busy} onClick={() => run(async () => { await createUser({ name: name.trim(), role }); setName(""); })}>
            Ajouter le profil
          </Button>
        </div>
      )}
      {error && <p className="text-[12.5px] text-danger">{error}</p>}
      <p className="text-[11.5px] text-text-faint">
        Le rôle donne les accès par défaut ; la direction peut en ajouter ou en retirer profil par profil. Les accès sont contrôlés par le serveur, pas seulement masqués à l&rsquo;écran. Pas de mot de passe dans cette version : un profil est une identité déclarée, pas une authentification.
      </p>
    </div>
  );
}
