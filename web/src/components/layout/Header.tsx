// ============================================================
// Component — Header (Glassmorphism Navigation Bar)
// ============================================================

import { useState, useEffect, useCallback } from 'react';
import { NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Layers, Clock, Settings, Menu, X } from 'lucide-react';
import { ThemeToggle } from '@/components/layout/ThemeToggle';
import './Header.css';

interface HeaderProps {
  isDark: boolean;
  onToggleTheme: () => void;
}

const navItems = [
  { to: '/', label: 'Home', icon: FileText },
  { to: '/batch', label: 'Batch Upload', icon: Layers },
  { to: '/history', label: 'History', icon: Clock },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const;

const mobileNavVariants = {
  hidden: { x: '100%' },
  visible: {
    x: 0,
    transition: { type: 'spring' as const, stiffness: 300, damping: 30 },
  },
  exit: {
    x: '100%',
    transition: { duration: 0.25, ease: 'easeIn' as const },
  },
};

const overlayVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
  exit: { opacity: 0 },
};

const linkStagger = {
  visible: {
    transition: { staggerChildren: 0.06, delayChildren: 0.1 },
  },
};

const linkItem = {
  hidden: { opacity: 0, x: 24 },
  visible: { opacity: 1, x: 0 },
};

export function Header({ isDark, onToggleTheme }: HeaderProps) {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Lock body scroll when mobile menu is open
  useEffect(() => {
    if (isMobileOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isMobileOpen]);

  const closeMobile = useCallback(() => setIsMobileOpen(false), []);

  const getNavLinkClass = (isActive: boolean, base: string, activeClass: string) =>
    isActive ? `${base} ${activeClass}` : base;

  return (
    <motion.header
      className={`header ${isScrolled ? 'header--scrolled' : ''}`}
      initial={{ y: -64, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <div className="header__inner">
        {/* Logo */}
        <NavLink to="/" className="header__logo" aria-label="PaperPulse AI — Home">
          <FileText className="header__logo-icon" />
          <span className="header__logo-text">
            PaperPulse AI
            <motion.span
              className="header__logo-underline"
              initial={{ width: 0 }}
              animate={{ width: '100%' }}
              transition={{ duration: 0.8, delay: 0.5, ease: 'easeOut' }}
            />
          </span>
        </NavLink>

        {/* Desktop Navigation */}
        <nav className="header__nav" aria-label="Main navigation">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                getNavLinkClass(isActive, 'header__nav-link', 'header__nav-link--active')
              }
            >
              <Icon className="header__nav-icon" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Right actions */}
        <div className="header__actions">
          <ThemeToggle isDark={isDark} onToggle={onToggleTheme} />

          {/* Hamburger (mobile) */}
          <motion.button
            className="header__hamburger"
            onClick={() => setIsMobileOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={isMobileOpen}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            type="button"
          >
            <Menu className="header__hamburger-icon" />
          </motion.button>
        </div>
      </div>

      {/* Mobile Slide-in Nav */}
      <AnimatePresence>
        {isMobileOpen && (
          <>
            <motion.div
              className="header__mobile-overlay"
              variants={overlayVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              onClick={closeMobile}
              aria-hidden="true"
            />
            <motion.nav
              className="header__mobile-nav"
              variants={mobileNavVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              aria-label="Mobile navigation"
            >
              <motion.button
                className="header__mobile-close"
                onClick={closeMobile}
                aria-label="Close navigation menu"
                whileHover={{ scale: 1.1 }}
                whileTap={{ scale: 0.9 }}
                type="button"
              >
                <X size={18} />
              </motion.button>

              <motion.div
                className="header__mobile-links"
                variants={linkStagger}
                initial="hidden"
                animate="visible"
              >
                {navItems.map(({ to, label, icon: Icon }) => (
                  <motion.div key={to} variants={linkItem}>
                    <NavLink
                      to={to}
                      end={to === '/'}
                      className={({ isActive }) =>
                        getNavLinkClass(isActive, 'header__mobile-link', 'header__mobile-link--active')
                      }
                      onClick={closeMobile}
                    >
                      <Icon className="header__nav-icon" />
                      {label}
                    </NavLink>
                  </motion.div>
                ))}
              </motion.div>

              <div className="header__mobile-theme">
                <span className="header__mobile-theme-label">Theme</span>
                <ThemeToggle isDark={isDark} onToggle={onToggleTheme} />
              </div>
            </motion.nav>
          </>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
