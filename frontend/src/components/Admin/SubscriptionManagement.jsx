import React, { useState, useEffect } from 'react';
import { 
  FaEdit, FaTrash, FaPlus, FaSave, FaTimes, FaSpinner,
  FaCheckCircle, FaExclamationTriangle, FaCrown, FaBolt,
  FaChartLine, FaUsers, FaMoneyBillWave, FaCog
} from 'react-icons/fa';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'react-hot-toast';

const API_URL = import.meta.env.VITE_API_BASE_URL;

const SubscriptionManagement = ({ user }) => {
  const [plans, setPlans] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [editingPlan, setEditingPlan] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [planForm, setPlanForm] = useState({
    plan_name: '',
    plan_description: '',
    price: 0,
    currency: 'INR',
    duration_days: 30,
    max_websites: 1,
    max_chat_messages: 1000,
    max_uploads: 10,
    features: [],
    is_active: true
  });
  const [newFeature, setNewFeature] = useState('');

  useEffect(() => {
    loadPlans();
    loadStats();
  }, []);

  const loadPlans = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/admin/subscription-plans`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      
      if (data.success) {
        setPlans(data.plans);
      } else {
        toast.error('Failed to load subscription plans');
      }
    } catch (error) {
      console.error('Error loading plans:', error);
      toast.error('Error loading subscription plans');
    } finally {
      setIsLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/admin/subscription-stats`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      
      if (data.success) {
        setStats(data.statistics);
      }
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  };

  const handleEditPlan = (plan) => {
    setEditingPlan(plan);
    setPlanForm({
      plan_name: plan.plan_name,
      plan_description: plan.plan_description || '',
      price: plan.price,
      currency: plan.currency || 'INR',
      duration_days: plan.duration_days || 30,
      max_websites: plan.max_websites || 1,
      max_chat_messages: plan.max_chat_messages || 1000,
      max_uploads: plan.max_uploads || 10,
      features: Array.isArray(plan.features) ? plan.features : [],
      is_active: plan.is_active === 1 || plan.is_active === true
    });
  };

  const handleSavePlan = async () => {
    // Validate form
    if (!planForm.plan_name.trim()) {
      toast.error('Plan name is required');
      return;
    }
    if (planForm.price <= 0) {
      toast.error('Price must be greater than 0');
      return;
    }
    if (planForm.duration_days <= 0) {
      toast.error('Duration must be greater than 0');
      return;
    }

    setIsSaving(true);
    try {
      const token = localStorage.getItem('access_token');
      const url = editingPlan 
        ? `${API_URL}/api/admin/subscription-plans/${editingPlan.id}`
        : `${API_URL}/api/admin/subscription-plans`;
      
      const response = await fetch(url, {
        method: editingPlan ? 'PUT' : 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(planForm)
      });
      
      const data = await response.json();
      
      if (data.success) {
        toast.success(data.message);
        setEditingPlan(null);
        setShowCreateModal(false);
        loadPlans();
        loadStats();
      } else {
        toast.error(data.error || 'Failed to save plan');
      }
    } catch (error) {
      console.error('Error saving plan:', error);
      toast.error('Error saving plan');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeletePlan = async (plan) => {
    if (!window.confirm(`Are you sure you want to delete the "${plan.plan_name}" plan?`)) {
      return;
    }
    
    try {
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_URL}/api/admin/subscription-plans/${plan.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      const data = await response.json();
      
      if (data.success) {
        toast.success(data.message);
        loadPlans();
        loadStats();
      } else {
        toast.error(data.error || 'Failed to delete plan');
      }
    } catch (error) {
      console.error('Error deleting plan:', error);
      toast.error('Error deleting plan');
    }
  };

  const handleAddFeature = () => {
    if (newFeature.trim()) {
      setPlanForm({
        ...planForm,
        features: [...planForm.features, newFeature.trim()]
      });
      setNewFeature('');
    }
  };

  const handleRemoveFeature = (index) => {
    setPlanForm({
      ...planForm,
      features: planForm.features.filter((_, i) => i !== index)
    });
  };

  const StatCard = ({ icon, title, value, color }) => (
    <div className={`bg-white rounded-xl p-6 shadow-lg border-l-4 border-${color}-500`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600 mb-1">{title}</p>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
        </div>
        <div className={`text-${color}-500 text-3xl`}>{icon}</div>
      </div>
    </div>
  );

  const PlanCard = ({ plan, onEdit, onDelete }) => {
    const isActive = plan.is_active === 1 || plan.is_active === true;
    const features = Array.isArray(plan.features) ? plan.features : [];
    
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className={`bg-white rounded-xl shadow-lg overflow-hidden border-2 transition-all ${
          isActive ? 'border-green-200 hover:shadow-xl' : 'border-gray-200 opacity-70'
        }`}
      >
        <div className="p-6">
          <div className="flex justify-between items-start mb-4">
            <div>
              <div className="flex items-center space-x-2">
                {plan.plan_name === 'Premium' ? (
                  <FaCrown className="text-yellow-500 text-2xl" />
                ) : (
                  <FaBolt className="text-blue-500 text-2xl" />
                )}
                <h3 className="text-xl font-bold text-gray-900">{plan.plan_name}</h3>
              </div>
              {!isActive && (
                <span className="inline-block mt-2 px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">
                  Inactive
                </span>
              )}
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => onEdit(plan)}
                className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                title="Edit Plan"
              >
                <FaEdit />
              </button>
              <button
                onClick={() => onDelete(plan)}
                className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                title="Delete Plan"
              >
                <FaTrash />
              </button>
            </div>
          </div>
          
          <div className="mb-4">
            <p className="text-3xl font-bold text-gray-900">
              ₹{plan.price}
              <span className="text-sm text-gray-500 font-normal">/{plan.duration_days === 1 ? 'day' : 'month'}</span>
            </p>
            <p className="text-sm text-gray-600 mt-2">{plan.plan_description}</p>
          </div>
          
          <div className="space-y-2 mb-4">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Websites</span>
              <span className="font-semibold text-gray-900">{plan.max_websites}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Chat Messages</span>
              <span className="font-semibold text-gray-900">{plan.max_chat_messages.toLocaleString()}/mo</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">File Uploads</span>
              <span className="font-semibold text-gray-900">{plan.max_uploads}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Duration</span>
              <span className="font-semibold text-gray-900">{plan.duration_days} days</span>
            </div>
          </div>
          
          {features.length > 0 && (
            <div className="border-t pt-4">
              <p className="text-sm font-semibold text-gray-900 mb-2">Features</p>
              <ul className="space-y-1">
                {features.slice(0, 3).map((feature, idx) => (
                  <li key={idx} className="flex items-center text-xs text-gray-600">
                    <FaCheckCircle className="text-green-500 mr-2 text-xs flex-shrink-0" />
                    {feature}
                  </li>
                ))}
                {features.length > 3 && (
                  <li className="text-xs text-blue-600">
                    +{features.length - 3} more features
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
      </motion.div>
    );
  };

  const PlanFormModal = ({ plan, onClose, onSave, isSaving }) => {
    const isEditing = !!plan;
    
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
          <div className="p-6 border-b border-gray-200 flex justify-between items-center sticky top-0 bg-white">
            <h2 className="text-xl font-bold text-gray-900">
              {isEditing ? 'Edit Subscription Plan' : 'Create New Subscription Plan'}
            </h2>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl"
            >
              &times;
            </button>
          </div>
          
          <div className="p-6 space-y-6">
            {/* Basic Information */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Plan Name *
              </label>
              <input
                type="text"
                value={planForm.plan_name}
                onChange={(e) => setPlanForm({ ...planForm, plan_name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="e.g., Standard, Premium, Enterprise"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Description
              </label>
              <textarea
                value={planForm.plan_description}
                onChange={(e) => setPlanForm({ ...planForm, plan_description: e.target.value })}
                rows="3"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="Brief description of the plan..."
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Price (₹) *
                </label>
                <input
                  type="number"
                  value={planForm.price}
                  onChange={(e) => setPlanForm({ ...planForm, price: parseFloat(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="0"
                  step="0.01"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Duration (days) *
                </label>
                <input
                  type="number"
                  value={planForm.duration_days}
                  onChange={(e) => setPlanForm({ ...planForm, duration_days: parseInt(e.target.value) || 30 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="1"
                />
              </div>
            </div>
            
            {/* Limits */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Max Websites
                </label>
                <input
                  type="number"
                  value={planForm.max_websites}
                  onChange={(e) => setPlanForm({ ...planForm, max_websites: parseInt(e.target.value) || 1 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="1"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Max Chat Messages
                </label>
                <input
                  type="number"
                  value={planForm.max_chat_messages}
                  onChange={(e) => setPlanForm({ ...planForm, max_chat_messages: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="0"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Max Uploads
                </label>
                <input
                  type="number"
                  value={planForm.max_uploads}
                  onChange={(e) => setPlanForm({ ...planForm, max_uploads: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  min="0"
                />
              </div>
            </div>
            
            {/* Features */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Features
              </label>
              <div className="flex gap-2 mb-3">
                <input
                  type="text"
                  value={newFeature}
                  onChange={(e) => setNewFeature(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleAddFeature()}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Add a feature (e.g., '24/7 Support')"
                />
                <button
                  onClick={handleAddFeature}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Add
                </button>
              </div>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {planForm.features.map((feature, index) => (
                  <div key={index} className="flex items-center justify-between bg-gray-50 p-2 rounded-lg">
                    <span className="text-sm text-gray-700">{feature}</span>
                    <button
                      onClick={() => handleRemoveFeature(index)}
                      className="text-red-500 hover:text-red-700"
                    >
                      <FaTimes />
                    </button>
                  </div>
                ))}
                {planForm.features.length === 0 && (
                  <p className="text-sm text-gray-500 text-center py-4">No features added yet</p>
                )}
              </div>
            </div>
            
            {/* Status */}
            <div className="flex items-center">
              <input
                type="checkbox"
                id="is_active"
                checked={planForm.is_active}
                onChange={(e) => setPlanForm({ ...planForm, is_active: e.target.checked })}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="is_active" className="ml-2 text-sm text-gray-700">
                Plan is active (visible to users)
              </label>
            </div>
          </div>
          
          <div className="p-6 border-t border-gray-200 flex justify-end space-x-3 sticky bottom-0 bg-white">
            <button
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onSave}
              disabled={isSaving}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              {isSaving && <FaSpinner className="animate-spin" />}
              <span>{isSaving ? 'Saving...' : 'Save Plan'}</span>
            </button>
          </div>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <FaSpinner className="animate-spin text-blue-600 text-3xl mx-auto mb-4" />
          <p className="text-gray-600">Loading subscription plans...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Subscription Plans Management</h2>
          <p className="text-gray-600 mt-1">Manage subscription plans, prices, and features</p>
        </div>
        <button
          onClick={() => {
            setEditingPlan(null);
            setPlanForm({
              plan_name: '',
              plan_description: '',
              price: 0,
              currency: 'INR',
              duration_days: 30,
              max_websites: 1,
              max_chat_messages: 1000,
              max_uploads: 10,
              features: [],
              is_active: true
            });
            setShowCreateModal(true);
          }}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
        >
          <FaPlus />
          <span>Create New Plan</span>
        </button>
      </div>

      {/* Statistics Cards */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <StatCard
            icon={<FaUsers className="text-blue-500" />}
            title="Active Subscriptions"
            value={stats.active_subscriptions || 0}
            color="blue"
          />
          <StatCard
            icon={<FaMoneyBillWave className="text-green-500" />}
            title="Total Revenue"
            value={`₹${(stats.total_revenue || 0).toLocaleString()}`}
            color="green"
          />
          <StatCard
            icon={<FaChartLine className="text-purple-500" />}
            title="Total Plans"
            value={plans.length}
            color="purple"
          />
        </div>
      )}

      {/* Plans Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {plans.map(plan => (
          <PlanCard
            key={plan.id}
            plan={plan}
            onEdit={handleEditPlan}
            onDelete={handleDeletePlan}
          />
        ))}
      </div>

      {plans.length === 0 && (
        <div className="text-center py-12 bg-white rounded-xl">
          <FaCog className="text-gray-400 text-4xl mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No Subscription Plans</h3>
          <p className="text-gray-600">Create your first subscription plan to get started</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Create Plan
          </button>
        </div>
      )}

      {/* Edit Modal */}
      {editingPlan && (
        <PlanFormModal
          plan={editingPlan}
          onClose={() => setEditingPlan(null)}
          onSave={handleSavePlan}
          isSaving={isSaving}
        />
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <PlanFormModal
          plan={null}
          onClose={() => setShowCreateModal(false)}
          onSave={handleSavePlan}
          isSaving={isSaving}
        />
      )}
    </div>
  );
};

export default SubscriptionManagement;