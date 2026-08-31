import type { Metadata } from 'next';
import { getSiteBrand } from '@/app/lib/site-brand-server';

export async function generateMetadata(): Promise<Metadata> {
  const brand = await getSiteBrand();
  return {
    title: 'Signal Run',
    description: `Guide a luminous ball through accelerating gates and solid hazards in ${brand.business_name}'s original 3D tunnel runner.`,
  };
}

export default function GameLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
