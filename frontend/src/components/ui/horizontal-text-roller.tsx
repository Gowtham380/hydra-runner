// @ts-ignore - JavaScript component with TS re-export
import HorizontalTextRoller from './horizontal-text-roller.jsx';

export interface HorizontalTextRollerProps {
  items: string[];
  selectedIndex?: number;
  onSelect?: (item: string, index: number) => void;
  activeScale?: number;
  inactiveScale?: number;
  activeOpacity?: number;
  inactiveOpacity?: number;
  className?: string;
}

export default HorizontalTextRoller;
