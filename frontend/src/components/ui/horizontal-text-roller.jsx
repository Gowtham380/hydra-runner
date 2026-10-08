import React, { useRef, useEffect, useState, useCallback } from 'react';
import { triggerHaptic } from '../../lib/telegram';

/**
 * Ultra-Compact Micro HorizontalTextRoller Component
 * - 3X Smaller sleek typography & padding (text-[11px], py-1 px-3)
 * - ONLY selected item is bold (font-black), unselected items are normal weight (font-normal)
 * - All items readable with elevated inactive opacity (0.65)
 * - Smooth center-zoom interpolation & snap
 * - Real-time scroll/drag center detection
 */
export default function HorizontalTextRoller({
  items = [],
  selectedIndex = 0,
  onSelect,
  activeScale = 1.08,
  inactiveScale = 0.92,
  activeOpacity = 1.0,
  inactiveOpacity = 0.65,
  className = '',
}) {
  const containerRef = useRef(null);
  const itemRefs = useRef([]);
  const [activeIdx, setActiveIdx] = useState(selectedIndex);
  const activeIdxRef = useRef(activeIdx);
  activeIdxRef.current = activeIdx;
  const scrollTimeoutRef = useRef(null);

  // Synchronize internal active state with external selectedIndex prop
  useEffect(() => {
    setActiveIdx(selectedIndex);
  }, [selectedIndex]);

  // Interpolate scale & opacity for each item based on distance from viewport center
  const updateItemScales = useCallback(() => {
    if (!containerRef.current) return 0;
    const container = containerRef.current;
    const containerCenter = container.scrollLeft + container.clientWidth / 2;

    let minDistance = Infinity;
    let closestIndex = 0;

    itemRefs.current.forEach((el, index) => {
      if (!el) return;
      const itemCenter = el.offsetLeft + el.clientWidth / 2;
      const distance = Math.abs(containerCenter - itemCenter);
      
      if (distance < minDistance) {
        minDistance = distance;
        closestIndex = index;
      }

      // Calculate normalized distance factor
      const maxDistance = container.clientWidth * 0.45;
      const factor = Math.min(distance / maxDistance, 1);

      // Smooth cosine easing interpolation
      const easeFactor = (1 - Math.cos(factor * Math.PI)) / 2;

      const scale = activeScale - easeFactor * (activeScale - inactiveScale);
      const opacity = activeOpacity - easeFactor * (activeOpacity - inactiveOpacity);

      el.style.transform = `scale(${scale.toFixed(3)})`;
      el.style.opacity = opacity.toFixed(3);
    });

    return closestIndex;
  }, [activeScale, inactiveScale, activeOpacity, inactiveOpacity]);

  // Scroll handler with requestAnimationFrame and scroll-settle selection update
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let animationFrameId;
    const onScroll = () => {
      animationFrameId = requestAnimationFrame(() => {
        const closestIdx = updateItemScales();

        if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
        scrollTimeoutRef.current = setTimeout(() => {
          if (closestIdx !== undefined && closestIdx !== activeIdxRef.current) {
            setActiveIdx(closestIdx);
            triggerHaptic();
            if (onSelect && items[closestIdx]) {
              onSelect(items[closestIdx], closestIdx);
            }
          }
        }, 100);
      });
    };

    container.addEventListener('scroll', onScroll, { passive: true });
    updateItemScales();

    return () => {
      container.removeEventListener('scroll', onScroll);
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    };
  }, [updateItemScales, items, onSelect]);

  // Center an item when clicked or externally selected
  const scrollToItem = useCallback((index) => {
    const el = itemRefs.current[index];
    const container = containerRef.current;
    if (!el || !container) return;
    const targetScroll = el.offsetLeft + el.clientWidth / 2 - container.clientWidth / 2;
    container.scrollTo({ left: targetScroll, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToItem(selectedIndex);
  }, [selectedIndex, scrollToItem]);

  return (
    <div className={`relative w-full py-1.5 overflow-hidden select-none ${className}`}>
      {/* Edge Vignette Gradient Fades */}
      <div className="absolute left-0 top-0 bottom-0 w-10 bg-gradient-to-r from-zinc-950 to-transparent z-10 pointer-events-none" />
      <div className="absolute right-0 top-0 bottom-0 w-10 bg-gradient-to-l from-zinc-950 to-transparent z-10 pointer-events-none" />

      {/* Subtle Center Guideline */}
      <div className="absolute left-1/2 top-1 bottom-1 -translate-x-1/2 w-0.5 bg-gradient-to-b from-transparent via-red-500/50 to-transparent pointer-events-none z-0" />

      {/* Main Horizontal Scroll Container */}
      <div
        ref={containerRef}
        className="flex items-center overflow-x-auto no-scrollbar py-1 cursor-grab active:cursor-grabbing snap-x snap-mandatory"
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        {/* Left Spacer */}
        <div className="w-[30vw] sm:w-[35vw] shrink-0 pointer-events-none" />

        {/* Text Roller Items */}
        {items.map((item, idx) => {
          const isSelected = idx === activeIdx;
          return (
            <button
              key={idx}
              ref={(el) => (itemRefs.current[idx] = el)}
              onClick={() => {
                setActiveIdx(idx);
                scrollToItem(idx);
                triggerHaptic();
                if (onSelect) onSelect(item, idx);
              }}
              className={`shrink-0 px-3 py-1 mx-1.5 rounded-full transition-all duration-200 cursor-pointer snap-center outline-none focus-visible:ring-2 focus-visible:ring-red-500 ${
                isSelected
                  ? 'bg-gradient-to-r from-red-600 to-rose-600 text-white font-black shadow-md shadow-red-950/60 border border-red-400/40'
                  : 'bg-zinc-900/90 text-zinc-400 font-normal border border-zinc-800 hover:text-zinc-200'
              }`}
              aria-label={`Select ${item}`}
            >
              <span className="text-[11px] uppercase tracking-wider whitespace-nowrap">
                {item}
              </span>
            </button>
          );
        })}

        {/* Right Spacer */}
        <div className="w-[30vw] sm:w-[35vw] shrink-0 pointer-events-none" />
      </div>
    </div>
  );
}

