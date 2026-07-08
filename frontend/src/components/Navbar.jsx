// src/components/Navbar.jsx

import React, { useState, useEffect, useRef } from 'react';
import { 
  FaRobot, FaUser, FaSignOutAlt, FaCog, FaChartBar, 
  FaHome, FaBars, FaTimes, FaBell, FaEnvelope, FaCrown, FaUserShield,
  FaExclamationTriangle, FaClock, FaCreditCard
} from 'react-icons/fa';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'react-hot-toast';
import { Link, useLocation, useNavigate } from 'react-router-dom';

const API_URL = import.meta.env.VITE_API_BASE_URL;

const Navbar = ({ user, onLogout, onLoginClick, onSignupClick }) => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);
  const [subscriptionNotification, setSubscriptionNotification] = useState(null);
  const [showSubscriptionAlert, setShowSubscriptionAlert] = useState(false);
  const [minutesRemaining, setMinutesRemaining] = useState(0);
  
  const location = useLocation();
  const navigate = useNavigate();
  const currentPath = location.pathname;

  // Refs for detecting hover outside
  const userMenuRef = useRef(null);
  const notificationRef = useRef(null);
  const userMenuTimerRef = useRef(null);
  const notificationTimerRef = useRef(null);

  // Check if user is admin
  const isAdmin = user?.role === 'admin';

  // Fetch subscription notification (only for non-admin users)
  useEffect(() => {
    if (user && !isAdmin) {
      fetchSubscriptionNotification();
      
      // Poll every minute for subscription status
      const interval = setInterval(fetchSubscriptionNotification, 60000);
      return () => clearInterval(interval);
    }
  }, [user, isAdmin]);

  const fetchSubscriptionNotification = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/user/notification`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        
        if (data.success) {
          setSubscriptionNotification(data.notification);
          setShowSubscriptionAlert(data.show_notification);
          setMinutesRemaining(data.minutes_remaining || 0);
          
          // Update unread notifications count
          if (data.show_notification) {
            setUnreadNotifications(1);
          } else {
            setUnreadNotifications(0);
          }
        }
      }
    } catch (error) {
      console.error('Error fetching notification:', error);
    }
  };

  const handleRechargeClick = () => {
    // Navigate to pricing page for recharge
    navigate('/pricing');
  };

  const handleSubscribeClick = () => {
    navigate('/pricing');
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isMenuOpen && !event.target.closest('nav')) {
        setIsMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isMenuOpen]);

  const handleLogout = async () => {
    try {
      const response = await fetch(`${API_URL}/api/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
          'Content-Type': 'application/json'
        }
      });
      
      localStorage.removeItem('access_token');
      localStorage.removeItem('user');
      
      toast.success('Logged out successfully');
      
      if (onLogout) {
        onLogout();
      }
    } catch (error) {
      console.error('Logout error:', error);
      toast.error('Logout failed');
    }
  };

  // User Menu Hover Handlers
  const handleUserMenuMouseEnter = () => {
    if (window.innerWidth >= 768) {
      clearTimeout(userMenuTimerRef.current);
      setShowUserMenu(true);
    }
  };

  const handleUserMenuMouseLeave = () => {
    if (window.innerWidth >= 768) {
      userMenuTimerRef.current = setTimeout(() => {
        setShowUserMenu(false);
      }, 300);
    }
  };

  const handleUserMenuClick = () => {
    if (window.innerWidth < 768) {
      setShowUserMenu(!showUserMenu);
    }
  };

  // Notification Hover Handlers
  const handleNotificationMouseEnter = () => {
    if (window.innerWidth >= 768) {
      clearTimeout(notificationTimerRef.current);
      setShowNotifications(true);
      setUnreadNotifications(0);
    }
  };

  const handleNotificationMouseLeave = () => {
    if (window.innerWidth >= 768) {
      notificationTimerRef.current = setTimeout(() => {
        setShowNotifications(false);
      }, 300);
    }
  };

  const handleNotificationClick = () => {
    if (window.innerWidth < 768) {
      setShowNotifications(!showNotifications);
      setUnreadNotifications(0);
    }
  };

  const handleDropdownMouseEnter = (type) => {
    if (window.innerWidth >= 768) {
      if (type === 'user') {
        clearTimeout(userMenuTimerRef.current);
      } else {
        clearTimeout(notificationTimerRef.current);
      }
    }
  };

  const handleDropdownMouseLeave = (type) => {
    if (window.innerWidth >= 768) {
      if (type === 'user') {
        userMenuTimerRef.current = setTimeout(() => {
          setShowUserMenu(false);
        }, 300);
      } else {
        notificationTimerRef.current = setTimeout(() => {
          setShowNotifications(false);
        }, 300);
      }
    }
  };

  const NotificationsDropdown = () => (
    <AnimatePresence>
      {showNotifications && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-2xl border border-gray-200 py-2 z-50"
          onMouseEnter={() => handleDropdownMouseEnter('notification')}
          onMouseLeave={() => handleDropdownMouseLeave('notification')}
          ref={notificationRef}
        >
          <div className="px-4 py-2 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900">Notifications</h3>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {subscriptionNotification && showSubscriptionAlert ? (
              <div className="px-4 py-3 border-b border-gray-100">
                <div className={`flex items-start space-x-3 ${
                  subscriptionNotification.type === 'danger' ? 'text-red-600' : 
                  subscriptionNotification.type === 'warning' ? 'text-orange-600' : 'text-blue-600'
                }`}>
                  {subscriptionNotification.type === 'danger' ? (
                    <FaExclamationTriangle className="mt-1 flex-shrink-0" />
                  ) : subscriptionNotification.type === 'warning' ? (
                    <FaClock className="mt-1 flex-shrink-0" />
                  ) : (
                    <FaBell className="mt-1 flex-shrink-0" />
                  )}
                  <div className="flex-1">
                    <p className="font-medium text-sm">{subscriptionNotification.message}</p>
                    {subscriptionNotification.details && (
                      <p className="text-xs text-gray-500 mt-1">{subscriptionNotification.details}</p>
                    )}
                    {minutesRemaining > 0 && (
                      <p className="text-xs text-orange-600 mt-1 font-medium">
                        {minutesRemaining} minutes remaining
                      </p>
                    )}
                    <button
                      onClick={subscriptionNotification.action === 'recharge' ? handleRechargeClick : handleSubscribeClick}
                      className={`mt-2 px-3 py-1 text-xs font-medium rounded-lg flex items-center space-x-1 ${
                        subscriptionNotification.type === 'danger' 
                          ? 'bg-red-100 text-red-700 hover:bg-red-200'
                          : subscriptionNotification.type === 'warning'
                          ? 'bg-orange-100 text-orange-700 hover:bg-orange-200'
                          : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                      }`}
                    >
                      <FaCreditCard />
                      <span>{subscriptionNotification.action_text}</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="px-4 py-6 text-center">
                <FaBell className="text-gray-400 text-2xl mx-auto mb-2" />
                <p className="text-gray-500 text-sm">No new notifications</p>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  const UserMenuDropdown = () => (
    <AnimatePresence>
      {showUserMenu && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-2xl border border-gray-200 py-2 z-50"
          onMouseEnter={() => handleDropdownMouseEnter('user')}
          onMouseLeave={() => handleDropdownMouseLeave('user')}
          ref={userMenuRef}
        >
          <div className="px-4 py-3 border-b border-gray-100">
            <p className="font-semibold text-gray-900">{user?.full_name}</p>
            <p className="text-sm text-gray-500">{user?.email}</p>
            {isAdmin && (
              <span className="inline-flex items-center px-2 py-1 mt-1 text-xs font-medium bg-purple-100 text-purple-800 rounded-full">
                <FaCrown className="mr-1" /> Admin
              </span>
            )}
          </div>
          
          <div className="py-1">
            <Link
              to="/dashboard"
              className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              <FaHome className="mr-3 text-gray-400" />
              Dashboard
            </Link>
            
            <Link
              to="/profile"
              className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              <FaUser className="mr-3 text-gray-400" />
              My Profile
            </Link>
            
            {/* REMOVED Subscription link - No longer show in dropdown */}
            
            {/* Admin specific links */}
            {isAdmin && (
              <Link
                to="/admin"
                className="flex items-center px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                <FaUserShield className="mr-3 text-gray-400" />
                Admin Panel
              </Link>
            )}
          </div>
          
          <div className="border-t border-gray-100 py-1">
            <button
              onClick={handleLogout}
              className="flex items-center w-full px-4 py-2 text-sm text-red-600 hover:bg-red-50 cursor-pointer"
            >
              <FaSignOutAlt className="mr-3" />
              Sign Out
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  // Subscription Alert Banner (Shown below navbar) - Only for non-admin users
  const SubscriptionAlertBanner = () => {
    if (isAdmin) return null;
    if (!showSubscriptionAlert || !subscriptionNotification) return null;
    
    return (
      <div className={`sticky top-16 z-30 ${
        subscriptionNotification.type === 'danger' ? 'bg-red-50 border-red-200' :
        subscriptionNotification.type === 'warning' ? 'bg-orange-50 border-orange-200' :
        'bg-blue-50 border-blue-200'
      } border-b shadow-sm`}>
        <div className="max-w-7xl mx-auto px-4 py-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center space-x-2">
              {subscriptionNotification.type === 'danger' ? (
                <FaExclamationTriangle className="text-red-600" />
              ) : subscriptionNotification.type === 'warning' ? (
                <FaClock className="text-orange-600" />
              ) : (
                <FaBell className="text-blue-600" />
              )}
              <span className={`text-sm font-medium ${
                subscriptionNotification.type === 'danger' ? 'text-red-800' :
                subscriptionNotification.type === 'warning' ? 'text-orange-800' :
                'text-blue-800'
              }`}>
                {subscriptionNotification.message}
              </span>
              {minutesRemaining > 0 && (
                <span className="text-xs font-bold bg-white px-2 py-0.5 rounded-full shadow-sm">
                  {minutesRemaining} min left
                </span>
              )}
            </div>
            <button
              onClick={subscriptionNotification.action === 'recharge' ? handleRechargeClick : handleSubscribeClick}
              className={`px-3 py-1 text-xs font-medium rounded-lg flex items-center space-x-1 transition-all ${
                subscriptionNotification.type === 'danger' 
                  ? 'bg-red-600 text-white hover:bg-red-700'
                  : subscriptionNotification.type === 'warning'
                  ? 'bg-orange-600 text-white hover:bg-orange-700'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
              }`}
            >
              <FaCreditCard />
              <span>{subscriptionNotification.action_text}</span>
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      <nav className="bg-white shadow-lg border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            {/* Logo and Brand */}
            <div className="flex items-center">
              <button
                onClick={() => setIsMenuOpen(!isMenuOpen)}
                className="md:hidden p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
              >
                {isMenuOpen ? <FaTimes /> : <FaBars />}
              </button>
              
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-lg">
                  <FaRobot className="text-white text-2xl" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-gray-900">Botrion</h1>
                </div>
              </div>
            </div>

            {/* Desktop Navigation - Right Side */}
            <div className="hidden md:flex items-center space-x-4">
              {user ? (
                <>
                  {/* Notifications - Only show for non-admin users */}
                  {!isAdmin && (
                    <div 
                      className="relative"
                      onMouseEnter={handleNotificationMouseEnter}
                      onMouseLeave={handleNotificationMouseLeave}
                    >
                      <button
                        onClick={handleNotificationClick}
                        className="p-2 text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-full transition-colors relative"
                      >
                        <FaBell />
                        {unreadNotifications > 0 && (
                          <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                            {unreadNotifications}
                          </span>
                        )}
                      </button>
                      <NotificationsDropdown />
                    </div>
                  )}
                  
                  {/* User Menu */}
                  <div 
                    className="relative"
                    onMouseEnter={handleUserMenuMouseEnter}
                    onMouseLeave={handleUserMenuMouseLeave}
                  >
                    <button
                      onClick={handleUserMenuClick}
                      className="cursor-pointer flex items-center space-x-3 p-2 rounded-xl hover:bg-gray-100 transition-colors"
                    >
                      <div className="w-8 h-8 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full flex items-center justify-center text-white font-semibold">
                        {user?.full_name?.charAt(0).toUpperCase()}
                      </div>
                      <div className="text-left hidden lg:block">
                        <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
                        <p className="text-xs text-gray-500">
                          {isAdmin ? 'Administrator' : 'User'}
                        </p>
                      </div>
                    </button>
                    <UserMenuDropdown />
                  </div>
                </>
              ) : (
                <>
                  <button
                    onClick={onLoginClick}
                    className="px-4 py-2 text-gray-700 hover:text-blue-600 hover:bg-blue-50 rounded-xl transition-colors font-medium cursor-pointer"
                  >
                    Sign In
                  </button>
                  <button
                    onClick={onSignupClick}
                    className="px-6 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl hover:from-blue-700 hover:to-indigo-700 transition-all duration-200 font-medium shadow-lg cursor-pointer"
                  >
                    Sign Up
                  </button>
                </>
              )}
            </div>

            {/* Mobile menu button */}
            {user && (
              <div className="md:hidden flex items-center">
                <button
                  onClick={handleUserMenuClick}
                  className="p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                >
                  <FaUser />
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Mobile Menu */}
        <AnimatePresence>
          {isMenuOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden border-t border-gray-200"
            >
              <div className="px-2 pt-2 pb-3 space-y-1">
                {user ? (
                  <>
                    <Link
                      to="/dashboard"
                      className="block px-3 py-2 rounded-md text-gray-700 hover:text-gray-900 hover:bg-gray-100"
                    >
                      Dashboard
                    </Link>
                    <Link
                      to="/profile"
                      className="block px-3 py-2 rounded-md text-gray-700 hover:text-gray-900 hover:bg-gray-100"
                    >
                      Profile
                    </Link>
                    
                    {/* REMOVED Subscription link - No longer show in mobile menu */}
                    
                    {isAdmin && (
                      <Link
                        to="/admin"
                        className="block px-3 py-2 rounded-md text-gray-700 hover:text-gray-900 hover:bg-gray-100"
                      >
                        Admin Panel
                      </Link>
                    )}
                    
                    <button
                      onClick={handleLogout}
                      className="block w-full text-left px-3 py-2 rounded-md text-red-600 hover:text-red-800 hover:bg-red-50 cursor-pointer"
                    >
                      Sign Out
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={onLoginClick}
                      className="block w-full text-left px-3 py-2 rounded-md text-gray-700 hover:text-gray-900 hover:bg-gray-100"
                    >
                      Sign In
                    </button>
                    <button
                      onClick={onSignupClick}
                      className="block w-full text-left px-3 py-2 rounded-md bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700"
                    >
                      Sign Up
                    </button>
                  </>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Mobile User Menu Dropdown */}
        {user && showUserMenu && window.innerWidth < 768 && (
          <div 
            className="md:hidden absolute right-4 mt-2 w-48 bg-white rounded-xl shadow-2xl border border-gray-200 py-2 z-50"
            ref={userMenuRef}
          >
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="font-semibold text-gray-900">{user.full_name}</p>
              <p className="text-sm text-gray-500">{user.email}</p>
              {isAdmin && (
                <span className="inline-flex items-center px-2 py-1 mt-1 text-xs font-medium bg-purple-100 text-purple-800 rounded-full">
                  <FaCrown className="mr-1" /> Admin
                </span>
              )}
            </div>
            <Link
              to="/dashboard"
              className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              Dashboard
            </Link>
            <Link
              to="/profile"
              className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
            >
              Profile
            </Link>
            
            {/* REMOVED Subscription link - No longer show in mobile dropdown */}
            
            {isAdmin && (
              <Link
                to="/admin"
                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                Admin Panel
              </Link>
            )}
            
            <button
              onClick={handleLogout}
              className="block w-full text-left px-4 py-2 text-red-600 hover:bg-red-50 cursor-pointer"
            >
              Sign Out
            </button>
          </div>
        )}
      </nav>
      
      {/* Subscription Alert Banner - Only for non-admin users */}
      <SubscriptionAlertBanner />
    </>
  );
};

export default Navbar;