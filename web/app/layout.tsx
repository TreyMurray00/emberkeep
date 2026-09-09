import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'Emberkeep · A Tabletop Chronicle',
  description:
    'Gather your party, create your character, and explore a living fantasy chronicle.',
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
