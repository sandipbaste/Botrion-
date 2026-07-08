// src/components/SubscriptionPlans.jsx

import React, { useState, useEffect } from 'react';
import { FaCheck, FaBolt, FaCrown, FaCreditCard, FaRocket, FaUserShield, FaArrowUp, FaLock } from 'react-icons/fa';
import { motion } from 'framer-motion';
import { toast } from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

const API_URL = import.meta.env.VITE_API_BASE_URL;

const SubscriptionPlans = ({ user, onSubscriptionPurchased, onBackToDashboard, refreshTrigger }) => {
  const [plans, setPlans] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [userSubscription, setUserSubscription] = useState(null);
  const [paymentSuccess, setPaymentSuccess] = useState(false);
  const [successfulSubscription, setSuccessfulSubscription] = useState(null);
  const [isRedirecting, setIsRedirecting] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
  if (user?.role === 'admin') {
    toast.info("Admins don't need subscriptions");
    navigate('/admin');
    return;
  }

  checkUserSubscription();

  const searchParams = new URLSearchParams(window.location.search);
  const paymentSuccessParam = searchParams.get('payment_success');

  if (paymentSuccessParam === 'true') {
    handlePaymentSuccess();
  }

  loadPlans(); // ✅ only here
}, [refreshTrigger]);

  const handlePaymentSuccess = () => {
    toast.success('Payment successful! Loading your subscription...');
    setPaymentSuccess(true);
    const newUrl = window.location.pathname;
    window.history.replaceState({}, document.title, newUrl);
    checkUserSubscription();
  };

  const loadPlans = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/payments/plans`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      
      if (data.success) {
        const formattedPlans = data.plans.map(plan => ({
          ...plan,
          max_chat_messages: plan.max_chat_messages || 0,
          max_websites: plan.max_websites || 0,
          max_uploads: plan.max_uploads || 0,
          price: plan.price || 0,
          duration_days: plan.duration_days || 30,
          features: Array.isArray(plan.features) ? plan.features : 
                   typeof plan.features === 'string' ? JSON.parse(plan.features || '[]') : []
        }));
        setPlans(formattedPlans);
      } else {
        toast.error('Failed to load subscription plans');
        setDefaultPlans();
      }
    } catch (error) {
      console.error('Error loading plans:', error);
      toast.error('Error loading subscription plans');
      setDefaultPlans();
    } finally {
      setIsLoading(false);
    }
  };

  const setDefaultPlans = () => {
    const defaultPlans = [
      {
        id: 1,
        plan_name: 'Standard',
        plan_description: 'Perfect for small businesses',
        price: 5,
        currency: 'INR',
        duration_days: 30,
        max_websites: 6,
        max_chat_messages: 5000,
        max_uploads: 20,
        features: [
          '6 websites',
          '5000 chat messages/month',
          '20 file uploads',
          'Basic support',
          'Email notifications'
        ]
      },
      {
        id: 2,
        plan_name: 'Premium',
        plan_description: 'For growing businesses',
        price: 10,
        currency: 'INR',
        duration_days: 30,
        max_websites: 10,
        max_chat_messages: 20000,
        max_uploads: 50,
        features: [
          '10 websites',
          '20000 chat messages/month',
          '50 file uploads',
          'Priority support',
          'Advanced analytics',
          'Custom branding',
          'API access'
        ]
      }
    ];
    setPlans(defaultPlans);
  };

  const checkUserSubscription = async () => {
    try {
      const token = localStorage.getItem('access_token');
      if (!token) return;
      
      const response = await fetch(`${API_URL}/api/payments/user-subscription`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success && data.has_subscription) {
          setUserSubscription(data.subscription);
          setSuccessfulSubscription(data.subscription);
          
          if (paymentSuccess) {
            setTimeout(() => {
              redirectToDashboard();
            }, 2000);
          }
        }
      }
    } catch (error) {
      console.error('Error checking subscription:', error);
    }
  };

  const initiatePayment = async (plan) => {
    setIsProcessing(true);
    setSelectedPlan(plan);
    
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        toast.error('Please login first');
        setIsProcessing(false);
        return;
      }
      
      const response = await fetch(`${API_URL}/api/payments/create-order`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ plan_id: plan.id })
      });
      
      const data = await response.json();
      
      if (data.success) {
        const ourOrderId = data.order_id;
        localStorage.setItem(`order_${plan.id}`, ourOrderId);
        
        if (data.payment_data && data.payment_data.razorpay_order_id) {
          const options = {
            key: data.payment_data.razorpay_key,
            amount: data.payment_data.amount,
            currency: data.payment_data.currency || 'INR',
            name: "Botrion",
            description: `Subscribe to ${plan.plan_name} Plan`,
            order_id: data.payment_data.razorpay_order_id,
            handler: async function (response) {
              await verifyPayment(response, plan, ourOrderId);
            },
            prefill: {
              name: user?.full_name || '',
              email: user?.email || '',
              contact: user?.mobile || ''
            },
            theme: { color: '#4F46E5' },
            modal: {
              ondismiss: function() {
                setIsProcessing(false);
                toast.info('Payment cancelled');
              }
            }
          };
          
          const razorpay = new window.Razorpay(options);
          razorpay.on('payment.failed', function(response) {
            toast.error(`Payment failed: ${response.error.description}`);
            setIsProcessing(false);
            localStorage.removeItem(`order_${plan.id}`);
          });
          
          razorpay.open();
        } else {
          toast.success(`Order created for ${plan.plan_name} plan`);
          setIsProcessing(false);
        }
      } else {
        toast.error(data.error || 'Failed to create payment order');
        setIsProcessing(false);
      }
    } catch (error) {
      console.error('Payment error:', error);
      toast.error('Failed to initiate payment');
      setIsProcessing(false);
    }
  };

  const verifyPayment = async (paymentResponse, plan, ourOrderId) => {
    try {
      const token = localStorage.getItem('access_token');
      
      const response = await fetch(`${API_URL}/api/payments/verify`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          razorpay_payment_id: paymentResponse.razorpay_payment_id,
          razorpay_order_id: paymentResponse.razorpay_order_id,
          razorpay_signature: paymentResponse.razorpay_signature,
          our_order_id: ourOrderId,
          plan_id: plan.id,
          user_id: user?.id
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setSuccessfulSubscription(data.subscription);
        setPaymentSuccess(true);
        toast.success(` Successfully subscribed to ${plan.plan_name} plan!`);
        
        localStorage.removeItem(`order_${plan.id}`);
        localStorage.setItem('user_subscription', JSON.stringify(data.subscription));
        setUserSubscription(data.subscription);
        
        if (onSubscriptionPurchased) {
          onSubscriptionPurchased();
        }
        
        setTimeout(() => {
          redirectToDashboard();
        }, 2000);
      } else {
        toast.error(data.error || 'Payment verification failed');
        localStorage.removeItem(`order_${plan.id}`);
      }
    } catch (error) {
      console.error('Verification error:', error);
      toast.error('Payment verification failed');
      localStorage.removeItem(`order_${plan.id}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const redirectToDashboard = () => {
    setIsRedirecting(true);
    navigate('/dashboard');
    if (onBackToDashboard) {
      onBackToDashboard();
    }
  };

  const PlanCard = ({ plan, index }) => {
    const isCurrentPlan = userSubscription && userSubscription.plan_name === plan.plan_name;
    const hasPremium = userSubscription?.plan_name === 'Premium';
    const hasStandard = userSubscription?.plan_name === 'Standard';
    const isPremiumPlan = plan.plan_name === 'Premium';
    const isStandardPlan = plan.plan_name === 'Standard';
    
    // Determine card state based on user's current plan
    let cardState = 'available'; // available, current, disabled
    
    if (isCurrentPlan) {
      // This is the user's current plan - they can recharge it
      cardState = 'recharge';
    } else if (hasPremium && isStandardPlan) {
      // User has Premium, Standard card should be disabled (cannot downgrade)
      cardState = 'disabled';
    } else if (hasStandard && isPremiumPlan) {
      // User has Standard, Premium card shows upgrade option
      cardState = 'upgrade';
    } else {
      // No subscription, or other cases
      cardState = 'available';
    }
    
    const getButtonText = () => {
      switch (cardState) {
        case 'recharge':
          return `Recharge ₹${plan.price}`;
        case 'upgrade':
          return `Upgrade for ₹${plan.price}`;
        case 'disabled':
          return 'Not Available';
        default:
          return `Subscribe for ₹${plan.price}`;
      }
    };
    
    const getButtonStyle = () => {
      switch (cardState) {
        case 'recharge':
          return 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700';
        case 'upgrade':
          return 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white hover:from-purple-700 hover:to-indigo-700';
        case 'disabled':
          return 'bg-gray-300 text-gray-500 cursor-not-allowed';
        default:
          return 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700';
      }
    };
    
    const handleClick = () => {
      if (cardState === 'disabled') {
        toast.info('You already have a Premium plan. Downgrade is not available.');
        return;
      }
      initiatePayment(plan);
    };
    
    const maxChatMessages = plan.max_chat_messages || 0;
    const maxWebsites = plan.max_websites || 0;
    const maxUploads = plan.max_uploads || 0;
    const price = plan.price || 0;
    const features = Array.isArray(plan.features) ? plan.features : [];
    
    return (
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: index * 0.1 }}
        className={`relative rounded-2xl p-8 transition-all duration-300 ${
          cardState === 'recharge'
            ? 'bg-gradient-to-br from-blue-50 to-indigo-50 border-2 border-blue-500 shadow-lg'
            : cardState === 'upgrade'
            ? 'bg-gradient-to-br from-purple-50 to-indigo-50 border-2 border-purple-500 shadow-xl transform scale-105'
            : cardState === 'disabled'
            ? 'bg-gray-100 border-2 border-gray-300 opacity-70'
            : 'bg-white border-2 border-gray-200 hover:border-blue-300 shadow-lg'
        }`}
      >
        {/* Badges */}
        {cardState === 'recharge' && (
          <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
            <span className="bg-gradient-to-r from-blue-500 to-indigo-600 text-white px-4 py-2 rounded-full text-sm font-bold shadow-lg">
              YOUR PLAN
            </span>
          </div>
        )}
        
        {cardState === 'upgrade' && (
          <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
            <span className="bg-gradient-to-r from-purple-500 to-indigo-600 text-white px-4 py-2 rounded-full text-sm font-bold shadow-lg flex items-center gap-2">
              <FaArrowUp />
              UPGRADE AVAILABLE
            </span>
          </div>
        )}
        
        {isPremiumPlan && !userSubscription && (
          <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
            <span className="bg-gradient-to-r from-yellow-400 to-orange-500 text-white px-4 py-2 rounded-full text-sm font-bold shadow-lg">
              MOST POPULAR
            </span>
          </div>
        )}
        
        <div className="text-center mb-6">
          <div className={`inline-flex p-4 rounded-2xl mb-4 ${
            cardState === 'recharge' ? 'bg-blue-200' :
            cardState === 'upgrade' ? 'bg-purple-200' :
            cardState === 'disabled' ? 'bg-gray-200' :
            'bg-blue-100'
          }`}>
            {isStandardPlan ? (
              <FaBolt className={`text-3xl ${
                cardState === 'recharge' ? 'text-blue-600' :
                cardState === 'upgrade' ? 'text-purple-600' :
                cardState === 'disabled' ? 'text-gray-500' :
                'text-blue-600'
              }`} />
            ) : (
              <FaCrown className={`text-3xl ${
                cardState === 'recharge' ? 'text-blue-600' :
                cardState === 'upgrade' ? 'text-purple-600' :
                cardState === 'disabled' ? 'text-gray-500' :
                'text-yellow-600'
              }`} />
            )}
          </div>
          
          <h3 className={`text-2xl font-bold mb-2 ${
            cardState === 'disabled' ? 'text-gray-500' : 'text-gray-900'
          }`}>
            {plan.plan_name}
          </h3>
          
          <div className="mb-4">
            <span className={`text-4xl font-bold ${
              cardState === 'disabled' ? 'text-gray-500' : 'text-gray-900'
            }`}>
              ₹{price}
            </span>
            <span className={`ml-2 ${
              cardState === 'disabled' ? 'text-gray-400' : 'text-gray-600'
            }`}>
              /month
            </span>
          </div>
          
          <p className={`${cardState === 'disabled' ? 'text-gray-400' : 'text-gray-600'} mb-6`}>
            {plan.plan_description}
          </p>
        </div>
        
        <div className="space-y-4 mb-8">
          <div className="flex items-center justify-between">
            <span className={cardState === 'disabled' ? 'text-gray-400' : 'text-gray-700'}>
              Websites
            </span>
            <span className={`font-bold ${cardState === 'disabled' ? 'text-gray-500' : 'text-gray-900'}`}>
              {maxWebsites}
            </span>
          </div>
          
          <div className="flex items-center justify-between">
            <span className={cardState === 'disabled' ? 'text-gray-400' : 'text-gray-700'}>
              Chat Messages
            </span>
            <span className={`font-bold ${cardState === 'disabled' ? 'text-gray-500' : 'text-gray-900'}`}>
              {maxChatMessages.toLocaleString()}/mo
            </span>
          </div>
          
          <div className="flex items-center justify-between">
            <span className={cardState === 'disabled' ? 'text-gray-400' : 'text-gray-700'}>
              File Uploads
            </span>
            <span className={`font-bold ${cardState === 'disabled' ? 'text-gray-500' : 'text-gray-900'}`}>
              {maxUploads}
            </span>
          </div>
          
          {features.length > 0 && (
            <div className="pt-4 border-t border-gray-300">
              <h4 className={`font-semibold mb-3 ${cardState === 'disabled' ? 'text-gray-500' : 'text-gray-900'}`}>
                Features
              </h4>
              <ul className="space-y-2">
                {features.map((feature, idx) => (
                  <li key={idx} className="flex items-center">
                    <FaCheck className={`mr-3 flex-shrink-0 ${
                      cardState === 'disabled' ? 'text-gray-400' : 'text-green-500'
                    }`} />
                    <span className={cardState === 'disabled' ? 'text-gray-400' : 'text-gray-700'}>
                      {feature}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        
        <button
          onClick={handleClick}
          disabled={cardState === 'disabled' || isProcessing}
          className={`w-full py-3 rounded-xl font-bold transition-all duration-200 flex items-center justify-center space-x-2 ${getButtonStyle()} disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isProcessing && selectedPlan?.id === plan.id ? (
            <>
              <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              <span>Processing...</span>
            </>
          ) : (
            <>
              {cardState === 'upgrade' && <FaArrowUp />}
              {cardState === 'disabled' && <FaLock />}
              <span>{getButtonText()}</span>
            </>
          )}
        </button>
        
        {cardState === 'recharge' && (
          <p className="text-xs text-blue-600 text-center mt-3">
            Recharge to extend your Standard plan for another month
          </p>
        )}
        
        {cardState === 'upgrade' && (
          <p className="text-xs text-purple-600 text-center mt-3">
            Upgrade from Standard to get more features and increase website limit to 10
          </p>
        )}
        
        {cardState === 'disabled' && (
          <p className="text-xs text-gray-500 text-center mt-3">
            You already have Premium plan
          </p>
        )}
      </motion.div>
    );
  };

  const PaymentSuccessModal = ({ subscription, onClose }) => (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden"
      >
        <div className="p-8 text-center">
          <div className="w-20 h-20 bg-gradient-to-r from-green-500 to-emerald-600 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Payment Successful! 
          </h2>
          
          <p className="text-gray-600 mb-6">
            {subscription?.plan_name === 'Premium' && userSubscription?.plan_name === 'Standard'
              ? `🎉 Congratulations! You've upgraded to ${subscription?.plan_name} plan!`
              : `You have successfully subscribed to the ${subscription?.plan_name} plan.`}
          </p>
          
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 mb-6">
            <div className="flex justify-between items-center mb-2">
              <span className="text-gray-700">Plan</span>
              <span className="font-bold text-gray-900">{subscription?.plan_name}</span>
            </div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-gray-700">Amount</span>
              <span className="font-bold text-green-600">₹{subscription?.price}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-700">Websites Allowed</span>
              <span className="font-bold text-gray-900">{subscription?.max_websites}</span>
            </div>
            {subscription?.plan_name === 'Premium' && userSubscription?.plan_name === 'Standard' && (
              <div className="mt-3 pt-3 border-t border-blue-200">
                <p className="text-sm text-purple-600 font-medium">
                  ✨ Your website limit increased from 6 to {subscription?.max_websites}!
                </p>
              </div>
            )}
          </div>
          
          <div className="flex space-x-4">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-3 border-2 border-gray-300 text-gray-700 font-medium rounded-xl hover:bg-gray-50 transition-colors"
            >
              Stay Here
            </button>
            <button
              onClick={redirectToDashboard}
              className="flex-1 px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-medium rounded-xl hover:from-blue-700 hover:to-indigo-700 transition-all duration-200"
            >
              Go to Dashboard
            </button>
          </div>
          
          <p className="text-sm text-gray-500 mt-4">
            Auto-redirecting in 2 seconds...
          </p>
        </div>
      </motion.div>
    </div>
  );

  if (user?.role === 'admin') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 bg-gradient-to-r from-purple-600 to-indigo-600 rounded-full flex items-center justify-center mx-auto mb-6">
            <FaUserShield className="text-white text-3xl" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Welcome Admin!</h1>
          <p className="text-gray-600 mb-6">As an administrator, you have full access to all features without any subscription.</p>
          <button onClick={() => navigate('/admin')} className="px-6 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-medium rounded-xl hover:from-purple-700 hover:to-indigo-700">
            Go to Admin Panel
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex items-center justify-center p-4">
        <div className="text-center">
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="w-full h-full border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
            <div className="absolute inset-0 flex items-center justify-center">
              <FaCreditCard className="text-blue-600 text-2xl" />
            </div>
          </div>
          <h3 className="text-xl font-semibold text-gray-800 mb-2">Loading Plans</h3>
          <p className="text-gray-600">Fetching subscription options...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {paymentSuccess && successfulSubscription && (
          <PaymentSuccessModal subscription={successfulSubscription} onClose={() => setPaymentSuccess(false)} />
        )}
        
        {isRedirecting && (
          <div className="fixed inset-0 bg-black/50 backdrop-blur-xs flex items-center justify-center z-50">
            <div className="bg-white rounded-2xl p-8 text-center">
              <div className="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mx-auto mb-4"></div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Redirecting to Dashboard</h3>
              <p className="text-gray-600">Please wait while we prepare your workspace...</p>
            </div>
          </div>
        )}
        
        <div className="text-center mb-12">
          <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="inline-flex p-3 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl mb-4">
            <FaRocket className="text-white text-2xl" />
          </motion.div>
          
          <motion.h1 initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }} className="text-4xl font-bold text-gray-900 mb-4">
            Manage Your Plan
          </motion.h1>
          
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="text-lg text-gray-600 max-w-2xl mx-auto">
            {userSubscription 
              ? `You are currently on the ${userSubscription.plan_name} plan. ${userSubscription.days_remaining > 0 ? `${userSubscription.days_remaining} days remaining.` : ''}`
              : 'Select the perfect plan to unlock all features and start creating amazing chatbots'}
          </motion.p>
          
          {userSubscription && userSubscription.plan_name === 'Standard' && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-6 inline-flex items-center px-4 py-2 bg-purple-100 text-purple-800 rounded-full">
              <FaArrowUp className="mr-2" />
              <span>Upgrade to Premium for more features and increase website limit to 10!</span>
            </motion.div>
          )}
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          {plans.map((plan, index) => (
            <PlanCard key={plan.id || index} plan={plan} index={index} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default SubscriptionPlans;