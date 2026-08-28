import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Dna,
  FlaskConical,
  Info,
  Microscope,
} from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();

  const links = [
    {
      path: '/',
      label: 'Analysis',
      icon: Microscope,
    },
    {
      path: '/methodology',
      label: 'Methodology',
      icon: FlaskConical,
    },
    {
      path: '/about',
      label: 'About',
      icon: Info,
    },
  ];

  return (
    <div className="min-h-screen bg-[#f6f8f8] text-ink">

      {/* TOP NAVIGATION */}
      <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-10">

          {/* BRAND */}
          <Link
            to="/"
            className="group flex items-center gap-3"
          >
            <div className="relative flex h-10 w-10 items-center justify-center overflow-hidden rounded-xl bg-ink shadow-sm">
              <Dna className="h-5 w-5 text-teal-300 transition-transform duration-300 group-hover:rotate-12" />

              <span className="absolute -right-2 -top-2 h-5 w-5 rounded-full bg-teal-400/20" />
            </div>

            <div className="leading-none">
              <div className="flex items-center gap-2">
                <span className="text-[15px] font-semibold tracking-tight text-ink">
                  NeuroCapstone
                </span>

                <span className="hidden rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[8px] font-semibold uppercase tracking-[0.14em] text-teal-700 sm:inline-flex">
                  Research
                </span>
              </div>

              <p className="mt-1 text-[9px] font-medium uppercase tracking-[0.14em] text-slate-400">
                Hybrid-Audit Platform
              </p>
            </div>
          </Link>

          {/* NAV */}
          <nav className="flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50/80 p-1">
            {links.map((link) => {
              const isActive =
                location.pathname === link.path;

              const Icon = link.icon;

              return (
                <Link
                  key={link.path}
                  to={link.path}
                  className={[
                    'relative flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition-all duration-200',
                    isActive
                      ? 'bg-white text-ink shadow-sm ring-1 ring-slate-200'
                      : 'text-slate-500 hover:bg-white/70 hover:text-slate-800',
                  ].join(' ')}
                >
                  <Icon
                    className={[
                      'h-3.5 w-3.5',
                      isActive
                        ? 'text-teal-700'
                        : 'text-slate-400',
                    ].join(' ')}
                  />

                  <span className="hidden sm:inline">
                    {link.label}
                  </span>

                  {isActive && (
                    <span className="absolute bottom-[-5px] left-1/2 h-0.5 w-5 -translate-x-1/2 rounded-full bg-teal-600" />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      {/* PAGE */}
      <main className="relative mx-auto w-full max-w-[1440px] px-5 py-8 sm:px-8 sm:py-10 lg:px-10">

        {/* subtle background decoration */}
        <div className="pointer-events-none absolute left-0 top-0 -z-0 h-64 w-64 rounded-full bg-teal-200/10 blur-3xl" />

        <div className="relative z-10">
          {children}
        </div>
      </main>

      {/* FOOTER */}
      <footer className="mt-16 border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-3 px-5 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-10">

          <div>
            <p className="text-[11px] font-medium text-slate-600">
              AI for Predicting Protein-Disease Associations in
              Neurodegenerative Disorders
            </p>

            <p className="mt-1 text-[9px] uppercase tracking-[0.12em] text-slate-400">
              NeuroCapstone Research Interface
            </p>
          </div>

          <div className="flex items-center gap-2 text-[9px] font-medium uppercase tracking-[0.12em] text-slate-400">
            <span className="h-1.5 w-1.5 rounded-full bg-teal-500" />
            Local research environment
          </div>
        </div>
      </footer>
    </div>
  );
}