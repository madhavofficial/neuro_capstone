import { useEffect, useRef } from 'react';
import { Box, Rotate3D, ZoomIn } from 'lucide-react';

interface ProteinViewerProps {
  pdbContent: string;
  variant?: string;
}

export default function ProteinViewer({
  pdbContent,
  variant,
}: ProteinViewerProps) {
  const viewerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let viewer: any = null;

    const setupViewer = async () => {
      if (!viewerRef.current || !pdbContent) return;

      const $3Dmol = await import('3dmol');

      viewer = $3Dmol.createViewer(viewerRef.current, {
        backgroundColor: '#0b1220',
      });

      viewer.addModel(pdbContent, 'pdb');

      viewer.setStyle(
        {},
        {
          cartoon: {
            color: 'spectrum',
            opacity: 0.92,
          },
        }
      );

      const match = variant?.match(/(\d+)/);
      const residueNumber = match ? Number(match[1]) : null;

      if (residueNumber !== null) {
        const residueSelection = {
          resi: residueNumber,
        };

        viewer.setStyle(
          residueSelection,
          {
            cartoon: {
              color: 'spectrum',
              opacity: 0.92,
            },
            stick: {
              color: '#ff3b30',
              radius: 0.28,
            },
          }
        );

        viewer.addLabel(`Mutation ${variant}`, {
          ...residueSelection,
          fontColor: 'white',
          backgroundColor: '#dc2626',
          backgroundOpacity: 0.85,
          fontSize: 12,
          padding: 4,
        });
      }

      viewer.setHoverable(
        {},
        true,
        function (atom: any) {
          viewer.addLabel(
            `${atom.resn} ${atom.resi} · Chain ${atom.chain}`,
            {
              atom,
              fontColor: 'white',
              backgroundColor: '#111827',
              backgroundOpacity: 0.85,
              fontSize: 11,
              padding: 3,
            }
          );
        },
        function () {
          viewer.removeAllLabels();
        }
      );

      viewer.zoomTo();
      viewer.zoom(1.05);
      viewer.render();

      const handleResize = () => {
        if (viewer) {
          viewer.resize();
          viewer.render();
        }
      };

      window.addEventListener('resize', handleResize);

      return () => {
        window.removeEventListener('resize', handleResize);
      };
    };

    let resizeCleanup: (() => void) | undefined;

    setupViewer().then((cleanup) => {
      resizeCleanup = cleanup;
    });

    return () => {
      resizeCleanup?.();

      if (viewer) {
        viewer.clear();
        viewer = null;
      }
    };
  }, [pdbContent, variant]);

  return (
    <div className="relative w-full overflow-hidden rounded-2xl border border-slate-800 bg-[#0b1220] shadow-inner">
      <div className="relative z-10 flex items-center justify-between border-b border-white/10 bg-[#0b1220] px-4 py-3">
        <div className="flex items-center gap-2">
          <Box className="h-4 w-4 text-teal-300" />
          <span className="text-xs font-semibold text-white">
            3D structural model
          </span>
        </div>

        <div className="flex items-center gap-3 text-[10px] text-slate-400">
          <span className="inline-flex items-center gap-1">
            <Rotate3D className="h-3 w-3" />
            Drag to rotate
          </span>
          <span className="inline-flex items-center gap-1">
            <ZoomIn className="h-3 w-3" />
            Scroll to zoom
          </span>
        </div>
      </div>

      <div
        ref={viewerRef}
        className="relative h-[430px] w-full min-w-0 overflow-hidden"
        style={{ position: 'relative' }}
        aria-label="Interactive 3D protein structure viewer"
      />

      <div className="relative z-10 flex items-center justify-between border-t border-white/10 bg-[#0b1220] px-4 py-3">
        <div className="flex items-center gap-2 text-[10px] text-slate-400">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
          Mutated residue
          {variant && (
            <span className="font-mono font-semibold text-slate-200">
              {variant}
            </span>
          )}
        </div>

        <span className="text-[10px] text-slate-500">
          Hover residues for labels
        </span>
      </div>
    </div>
  );
}
