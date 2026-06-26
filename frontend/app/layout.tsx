import type { Metadata } from 'next';
import { Poppins } from 'next/font/google';
import './globals.css';

const sans = Poppins({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-sans',
  display: 'swap',
});

// Poppins for the trace ribbon too (used via --font-mono).
const mono = Poppins({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Relationship Desk — Banking CRM Assistant',
  description: 'Find high-potential customers, see why they rank, and draft outreach.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
