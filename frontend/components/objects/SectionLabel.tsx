// The section heading style every object page already uses (V1 detail pages).
export default function SectionLabel({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <span id={id} className="mb-4 block scroll-mt-6 text-[11.5px] font-bold tracking-wide text-text-faint uppercase">
      {children}
    </span>
  );
}
