/**
 * SMD DOWNLOADER / PROJECT HYDRA - TELEGRAM MINI APP SDK & HAPTIC UTILITY
 * Decoupled fallback implementation for Telegram WebApp environment
 */

export function initTelegramApp() {
  try {
    if (typeof window !== 'undefined') {
      const tg = window.Telegram?.WebApp;
      if (tg) {
        if (typeof tg.ready === 'function') tg.ready();
        if (typeof tg.expand === 'function') tg.expand();
        if (typeof tg.setHeaderColor === 'function') tg.setHeaderColor('#0f172a');
        if (typeof tg.setBackgroundColor === 'function') tg.setBackgroundColor('#0f172a');
      }
    }
  } catch (e) {
    console.warn('Telegram SDK init warning:', e);
  }
}

export function triggerHaptic(style = 'light') {
  try {
    if (typeof window !== 'undefined' && window.Telegram?.WebApp?.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
    }
  } catch (e) {
    // Non-telegram environment fallback
  }
}

export function useTelegramBackButton(onClickHandler) {
  try {
    if (typeof window !== 'undefined' && window.Telegram?.WebApp?.BackButton) {
      const backBtn = window.Telegram.WebApp.BackButton;
      if (onClickHandler) {
        backBtn.show();
        backBtn.onClick(onClickHandler);
        return () => {
          backBtn.offClick(onClickHandler);
          backBtn.hide();
        };
      } else {
        backBtn.hide();
      }
    }
  } catch (e) {
    console.warn('Telegram BackButton note:', e);
  }
  return () => {};
}

export function getTelegramUserInfo() {
  try {
    if (typeof window !== 'undefined' && window.Telegram?.WebApp?.initDataUnsafe?.user) {
      return window.Telegram.WebApp.initDataUnsafe.user;
    }
    return null;
  } catch (e) {
    return null;
  }
}

export function openExternalLink(url) {
  if (!url) return;
  try {
    if (typeof window !== 'undefined' && window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(url, { try_instant_view: false });
    } else {
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  } catch (e) {
    window.open(url, '_blank', 'noopener,noreferrer');
  }
}

export default typeof window !== 'undefined' ? (window.Telegram?.WebApp || {}) : {};
