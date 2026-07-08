// src/components/Admin/UserDetailsModal.jsx

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { 
  FaUser, FaEnvelope, FaCalendar, FaRobot, FaComments, 
  FaEnvelopeOpenText, FaFileUpload, FaCrown, FaTimes,
  FaSpinner, FaCheckCircle, FaExclamationTriangle, FaClock,
  FaUserShield, FaUserCheck, FaUserTimes, FaDatabase, 
  FaGlobe, FaLock, FaCopy, FaCheck, FaChartBar, 
  FaDownload, FaFileExcel, FaFilePdf
} from 'react-icons/fa';
import { Link } from 'react-router-dom';
import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { toast } from 'react-hot-toast';

const UserDetailsModal = ({ isOpen, onClose, user, isLoading }) => {
  const modalRef = useRef(null);
  const dropdownRef = useRef(null);
  const [copiedStates, setCopiedStates] = useState({});
  const [isExporting, setIsExporting] = useState(false);
  const [showExportDropdown, setShowExportDropdown] = useState(false);

  // Helper Functions
  const getPlanBadge = (plan) => {
    if (!plan) {
      return <span className="px-2 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-full">No Plan</span>;
    }
    if (plan === 'Premium') {
      return <span className="px-2 py-1 bg-gradient-to-r from-yellow-500 to-orange-500 text-white text-xs font-medium rounded-full flex items-center gap-1">
        <FaCrown className="text-xs" />
        Premium
      </span>;
    }
    return <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">Standard</span>;
  };

  const getStatusBadge = (isActive) => {
    if (isActive) {
      return <span className="px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full flex items-center gap-1">
        <FaCheckCircle className="text-xs" />
        Active
      </span>;
    }
    return <span className="px-2 py-1 bg-red-100 text-red-800 text-xs font-medium rounded-full flex items-center gap-1">
      <FaExclamationTriangle className="text-xs" />
      Inactive
    </span>;
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  const formatDateTime = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getDaysRemaining = (endDate) => {
    if (!endDate) return null;
    const end = new Date(endDate);
    const now = new Date();
    const diffTime = end - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  };

  const daysRemaining = getDaysRemaining(user?.subscription_end_date);

  // Copy script handler
  const handleCopyScript = useCallback((websiteId, scriptTag) => {
    navigator.clipboard.writeText(scriptTag);
    setCopiedStates(prev => ({ ...prev, [websiteId]: true }));
    toast.success('Script tag copied to clipboard!');
    setTimeout(() => {
      setCopiedStates(prev => ({ ...prev, [websiteId]: false }));
    }, 2000);
  }, []);

  // ==================== PDF EXPORT ====================
  const handleGeneratePDF = useCallback(async () => {
    if (!user) return;
    
    setIsExporting(true);
    setShowExportDropdown(false);
    
    try {
      const doc = new jsPDF({
        orientation: 'portrait',
        unit: 'mm',
        format: 'a4'
      });
      
      let yPos = 20;
      
      const addText = (text, fontSize = 12, isBold = false, x = 14) => {
        doc.setFontSize(fontSize);
        doc.setFont('helvetica', isBold ? 'bold' : 'normal');
        doc.text(text, x, yPos);
        yPos += fontSize / 2 + 2;
      };
      
      // Title
      doc.setTextColor(102, 126, 234);
      doc.setFontSize(24);
      doc.setFont('helvetica', 'bold');
      doc.text('User Report', 14, yPos);
      yPos += 15;
      
      // Generated Date
      doc.setTextColor(100, 100, 100);
      doc.setFontSize(10);
      doc.setFont('helvetica', 'normal');
      doc.text(`Generated: ${new Date().toLocaleString()}`, 14, yPos);
      yPos += 8;
      doc.text(`Report ID: RPT-${user.id}-${Date.now()}`, 14, yPos);
      yPos += 8;
      doc.text(`Exported by: Admin`, 14, yPos);
      yPos += 15;
      
      // User Information Section
      doc.setTextColor(51, 51, 51);
      doc.setFontSize(16);
      doc.setFont('helvetica', 'bold');
      doc.text(' User Information', 14, yPos);
      yPos += 10;
      
      // User Info Table with Subscription
      const userInfoData = [
        ['User ID', user.id.toString()],
        ['Full Name', user.full_name || 'N/A'],
        ['Email', user.email || 'N/A'],
        ['Mobile', user.mobile || 'Not provided'],
        ['Status', user.is_active ? 'Active' : 'Inactive'],
        ['Role', user.role || 'user'],
        ['Subscription Plan', user.subscription_plan || 'No Plan'],
        ['Subscription End Date', user.subscription_end_date ? formatDateTime(user.subscription_end_date) : 'N/A'],
        ['Days Remaining', daysRemaining > 0 ? `${daysRemaining} days` : daysRemaining === 0 ? 'Expires Today' : 'Expired'],
        ['Joined Date', new Date(user.created_at).toLocaleString()]
      ];
      
      autoTable(doc, {
        startY: yPos,
        head: [['Field', 'Value']],
        body: userInfoData,
        theme: 'grid',
        headStyles: { fillColor: [102, 126, 234], textColor: 255, fontStyle: 'bold' },
        columnStyles: { 0: { fontStyle: 'bold', cellWidth: 50 }, 1: { cellWidth: 130 } },
        margin: { left: 14, right: 14 }
      });
      
      yPos = doc.lastAutoTable.finalY + 15;
      
      // Statistics Section
      if (user.stats) {
        doc.setFontSize(16);
        doc.setFont('helvetica', 'bold');
        doc.text(' User Statistics', 14, yPos);
        yPos += 10;
        
        const statsData = [
          ['Total Websites', user.stats.total_websites?.toString() || '0'],
          ['Total Chat Messages', user.stats.total_chat_messages?.toString() || '0'],
          ['Total Contact Forms', user.stats.total_contact_forms?.toString() || '0'],
          ['Total Uploaded Files', user.stats.total_uploaded_files?.toString() || '0']
        ];
        
        autoTable(doc, {
          startY: yPos,
          head: [['Metric', 'Count']],
          body: statsData,
          theme: 'grid',
          headStyles: { fillColor: [72, 187, 120], textColor: 255, fontStyle: 'bold' },
          columnStyles: { 0: { fontStyle: 'bold', cellWidth: 80 }, 1: { cellWidth: 100 } },
          margin: { left: 14, right: 14 }
        });
        
        yPos = doc.lastAutoTable.finalY + 15;
      }
      
      // Websites Section
      if (user.websites && user.websites.length > 0) {
        doc.setFontSize(16);
        doc.setFont('helvetica', 'bold');
        doc.text(` All Websites (${user.websites.length})`, 14, yPos);
        yPos += 10;
        
        user.websites.forEach((website, index) => {
          if (yPos > 250) {
            doc.addPage();
            yPos = 20;
          }
          
          doc.setFontSize(14);
          doc.setFont('helvetica', 'bold');
          doc.setTextColor(102, 126, 234);
          doc.text(`Website #${index + 1} - ${website.status?.toUpperCase() || 'UNKNOWN'}`, 14, yPos);
          yPos += 8;
          
          doc.setTextColor(51, 51, 51);
          doc.setFontSize(10);
          
          const websiteData = [
            ['Website ID', website.website_id || 'N/A'],
            ['Website Name', website.website_name || 'N/A'],
            ['Website URL', website.website_url || 'N/A'],
            ['Created Date', website.created_at ? new Date(website.created_at).toLocaleString() : 'N/A'],
            ['Chat Messages', website.chat_messages_count?.toString() || '0'],
            ['Contact Forms', website.contact_forms_count?.toString() || '0'],
            ['Uploaded Files', website.files_count?.toString() || '0']
          ];
          
          autoTable(doc, {
            startY: yPos,
            body: websiteData,
            theme: 'plain',
            columnStyles: { 0: { fontStyle: 'bold', cellWidth: 40 }, 1: { cellWidth: 140 } },
            margin: { left: 14, right: 14 },
            styles: { fontSize: 9 }
          });
          
          yPos = doc.lastAutoTable.finalY + 5;
          
          if (website.script_tag) {
            doc.setFontSize(10);
            doc.setFont('helvetica', 'bold');
            doc.text('Script Tag:', 14, yPos);
            yPos += 5;
            
            doc.setFont('courier', 'normal');
            doc.setFontSize(8);
            
            const splitScript = doc.splitTextToSize(website.script_tag, 170);
            doc.text(splitScript, 14, yPos);
            yPos += splitScript.length * 4 + 5;
          } else {
            doc.setFontSize(10);
            doc.setFont('helvetica', 'italic');
            doc.setTextColor(150, 150, 150);
            doc.text('No script tag generated', 14, yPos);
            yPos += 8;
            doc.setTextColor(51, 51, 51);
          }
          
          yPos += 10;
        });
      }
      
      // Footer
      doc.setFontSize(8);
      doc.setTextColor(150, 150, 150);
      doc.text('© Chatbot Generator - Admin Panel', 14, 285);
      doc.text('This report is confidential', 14, 290);
      
      doc.save(`user_${user.id}_${user.full_name?.replace(/\s+/g, '_')}_report_${new Date().toISOString().split('T')[0]}.pdf`);
      
      toast.success('PDF report generated successfully!');
    } catch (error) {
      console.error('Error generating PDF:', error);
      toast.error('Failed to generate PDF report');
    } finally {
      setIsExporting(false);
    }
  }, [user, formatDateTime, daysRemaining]);

  // ==================== EXCEL EXPORT ====================
  const handleDownloadExcel = useCallback(() => {
    if (!user) return;
    
    setIsExporting(true);
    setShowExportDropdown(false);
    
    try {
      const wb = XLSX.utils.book_new();
      
      // ===== SHEET 1: User Information =====
      const userInfoData = [
        ['USER INFORMATION', ''],
        ['Generated Date', new Date().toLocaleString()],
        ['Report ID', `RPT-${user.id}-${Date.now()}`],
        ['Exported By', 'Admin Panel'],
        ['', ''],
        ['User Details', ''],
        ['User ID', user.id],
        ['Full Name', user.full_name || 'N/A'],
        ['Email Address', user.email || 'N/A'],
        ['Mobile Number', user.mobile || 'Not provided'],
        ['Account Status', user.is_active ? 'Active' : 'Inactive'],
        ['User Role', user.role || 'user'],
        ['Subscription Plan', user.subscription_plan || 'No Plan'],
        ['Subscription End Date', user.subscription_end_date ? formatDateTime(user.subscription_end_date) : 'N/A'],
        ['Days Remaining', daysRemaining > 0 ? `${daysRemaining} days` : daysRemaining === 0 ? 'Expires Today' : 'Expired'],
        ['Joined Date', new Date(user.created_at).toLocaleString()],
        ['', ''],
        ['STATISTICS (All Websites)', ''],
        ['Total Websites', user.stats?.total_websites || 0],
        ['Total Chat Messages', user.stats?.total_chat_messages || 0],
        ['Total Contact Forms', user.stats?.total_contact_forms || 0],
        ['Total Uploaded Files', user.stats?.total_uploaded_files || 0]
      ];
      
      const userInfoSheet = XLSX.utils.aoa_to_sheet(userInfoData);
      userInfoSheet['!cols'] = [{ wch: 25 }, { wch: 50 }];
      XLSX.utils.book_append_sheet(wb, userInfoSheet, 'User Information');
      
      // ===== SHEET 2: All Websites =====
      if (user.websites && user.websites.length > 0) {
        const websitesData = [
          ['WEBSITE DETAILS', '', '', '', '', '', '', '', '', ''],
          ['Website #', 'Website ID', 'Website Name', 'Website URL', 'Status', 'Created Date', 'Chat Messages', 'Contact Forms', 'Uploaded Files', 'Script Generated', 'Script Tag']
        ];
        
        user.websites.forEach((website, index) => {
          websitesData.push([
            (index + 1).toString(),
            website.website_id || 'N/A',
            website.website_name || 'N/A',
            website.website_url || 'N/A',
            website.status || 'unknown',
            website.created_at ? new Date(website.created_at).toLocaleString() : 'N/A',
            (website.chat_messages_count || 0).toString(),
            (website.contact_forms_count || 0).toString(),
            (website.files_count || 0).toString(),
            website.script_tag ? 'Yes' : 'No',
            website.script_tag || ''
          ]);
        });
        
        const websitesSheet = XLSX.utils.aoa_to_sheet(websitesData);
        websitesSheet['!cols'] = [
          { wch: 8 }, { wch: 20 }, { wch: 25 }, { wch: 40 }, { wch: 12 },
          { wch: 20 }, { wch: 15 }, { wch: 15 }, { wch: 15 }, { wch: 15 }, { wch: 60 }
        ];
        
        XLSX.utils.book_append_sheet(wb, websitesSheet, 'Websites');
      }
      
      // ===== SHEET 3: Website Statistics Summary =====
      if (user.websites && user.websites.length > 0) {
        const summaryData = [
          ['WEBSITE STATISTICS SUMMARY', '', '', ''],
          ['Website Name', 'Chat Messages', 'Contact Forms', 'Uploaded Files']
        ];
        
        user.websites.forEach(website => {
          summaryData.push([
            website.website_name || 'N/A',
            (website.chat_messages_count || 0).toString(),
            (website.contact_forms_count || 0).toString(),
            (website.files_count || 0).toString()
          ]);
        });
        
        const totalChat = user.websites.reduce((sum, w) => sum + (w.chat_messages_count || 0), 0);
        const totalForms = user.websites.reduce((sum, w) => sum + (w.contact_forms_count || 0), 0);
        const totalFiles = user.websites.reduce((sum, w) => sum + (w.files_count || 0), 0);
        
        summaryData.push(['TOTAL', totalChat.toString(), totalForms.toString(), totalFiles.toString()]);
        
        const summarySheet = XLSX.utils.aoa_to_sheet(summaryData);
        summarySheet['!cols'] = [{ wch: 30 }, { wch: 15 }, { wch: 15 }, { wch: 15 }];
        XLSX.utils.book_append_sheet(wb, summarySheet, 'Statistics Summary');
      }
      
      // ===== SHEET 4: Export Information =====
      const exportInfoData = [
        ['EXPORT INFORMATION', ''],
        ['Generated Date', new Date().toLocaleString()],
        ['Generated Date (ISO)', new Date().toISOString()],
        ['Exported By', 'Admin Panel'],
        ['Report ID', `RPT-${user.id}-${Date.now()}`],
        ['User ID', user.id],
        ['User Email', user.email || 'N/A'],
        ['User Subscription Plan', user.subscription_plan || 'No Plan'],
        ['Total Websites', user.websites?.length || 0],
        ['Version', '1.0']
      ];
      
      const exportInfoSheet = XLSX.utils.aoa_to_sheet(exportInfoData);
      exportInfoSheet['!cols'] = [{ wch: 25 }, { wch: 40 }];
      XLSX.utils.book_append_sheet(wb, exportInfoSheet, 'Export Info');
      
      XLSX.writeFile(wb, `user_${user.id}_${user.full_name?.replace(/\s+/g, '_')}_full_report_${new Date().toISOString().split('T')[0]}.xlsx`);
      
      toast.success('Excel file downloaded successfully!');
    } catch (error) {
      console.error('Error downloading Excel:', error);
      toast.error('Failed to download Excel');
    } finally {
      setIsExporting(false);
    }
  }, [user, formatDateTime, daysRemaining]);

  const handleClickOutside = useCallback((event) => {
    if (modalRef.current && !modalRef.current.contains(event.target)) {
      onClose();
    }
    if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
      setShowExportDropdown(false);
    }
  }, [onClose]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.body.style.overflow = 'auto';
    };
  }, [isOpen, handleClickOutside]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm" 
        aria-hidden="true"
      />
      
      <div className="flex items-center justify-center min-h-screen p-4">
        <motion.div
          ref={modalRef}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          className="relative bg-white rounded-2xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-y-auto"
        >
          <div className="p-6">
            {/* Header with Export Dropdown */}
            <div className="flex justify-between items-start mb-6 sticky top-0 bg-white z-10 pb-4 border-b">
              <div className="flex items-center space-x-3">
                <div className="w-12 h-12 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-xl flex items-center justify-center">
                  <FaUserShield className="text-white text-xl" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-gray-900">User Details</h3>
                  <p className="text-sm text-gray-600">View complete user information and all websites</p>
                </div>
              </div>
              
              <div className="flex items-center space-x-2">
                {/* Export Dropdown Button */}
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => setShowExportDropdown(!showExportDropdown)}
                    disabled={isExporting || !user}
                    className="cursor-pointer px-4 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-700 hover:to-emerald-700 transition-all duration-200 flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    type="button"
                  >
                    {isExporting ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        <span>Exporting...</span>
                      </>
                    ) : (
                      <>
                        <FaDownload className="text-sm" />
                        <span>Export Data</span>
                      </>
                    )}
                  </button>
                  
                  {/* Export Dropdown Menu */}
                  {showExportDropdown && !isExporting && (
                    <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-2xl border border-gray-200 z-20 overflow-hidden animate-fadeIn">
                      <div className="py-1">
                        <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
                          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Export Format</p>
                        </div>
                        
                        <button
                          onClick={handleDownloadExcel}
                          className="cursor-pointer w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center space-x-3 transition-colors border-t border-gray-100"
                          type="button"
                        >
                          <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
                            <FaFileExcel className="text-emerald-600" size={16} />
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-gray-900">Excel Format</p>
                            <p className="text-xs text-gray-500">Multiple sheets with full data</p>
                          </div>
                          <span className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-600">.xlsx</span>
                        </button>
                        
                        <div className="border-t border-gray-200 my-1"></div>
                        
                        <button
                          onClick={handleGeneratePDF}
                          className="cursor-pointer w-full px-4 py-3 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center space-x-3 transition-colors"
                          type="button"
                        >
                          <div className="w-8 h-8 bg-red-100 rounded-lg flex items-center justify-center">
                            <FaFilePdf className="text-red-600" size={16} />
                          </div>
                          <div className="flex-1">
                            <p className="font-medium text-gray-900">PDF Report</p>
                            <p className="text-xs text-gray-500">Professional formatted report</p>
                          </div>
                          <span className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-600">.pdf</span>
                        </button>
                      </div>
                    </div>
                  )}
                </div>
                
                <button
                  onClick={onClose}
                  className="cursor-pointer text-gray-400 hover:text-gray-600 p-2 rounded-full hover:bg-gray-100 transition-colors"
                  type="button"
                  aria-label="Close modal"
                >
                  <FaTimes className="text-xl" />
                </button>
              </div>
            </div>

            {/* Modal Content */}
            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="w-12 h-12 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mb-4"></div>
                <p className="text-gray-600">Loading user details...</p>
              </div>
            ) : user ? (
              <div className="space-y-6">
                {/* User Information Section with Subscription Plan */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                  {/* Personal Information */}
                  <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
                    <h3 className="font-semibold text-gray-900 mb-3 flex items-center">
                      <FaUser className="mr-2 text-blue-600" />
                      Personal Information
                    </h3>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">User ID</span>
                        <span className="font-medium text-gray-900">{user.id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">Full Name</span>
                        <span className="font-medium text-gray-900">{user.full_name || 'N/A'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">Email</span>
                        <span className="font-medium text-gray-900 break-all">{user.email || 'N/A'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">Mobile</span>
                        <span className="font-medium text-gray-900">{user.mobile || 'N/A'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">Role</span>
                        <span className="font-medium text-gray-900 capitalize">{user.role || 'User'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">Joined</span>
                        <span className="font-medium text-gray-900">{formatDate(user.created_at)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600 text-sm">Status</span>
                        {getStatusBadge(user.is_active)}
                      </div>
                    </div>
                  </div>

                  {/* Subscription Plan Information */}
                  <div className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-xl p-4 border border-purple-100">
                    <h3 className="font-semibold text-gray-900 mb-3 flex items-center">
                      <FaCrown className="mr-2 text-yellow-600" />
                      Subscription Plan
                    </h3>
                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-600 text-sm">Current Plan</span>
                        {getPlanBadge(user.subscription_plan)}
                      </div>
                      {user.subscription_end_date && (
                        <>
                          <div className="flex justify-between">
                            <span className="text-gray-600 text-sm">Valid Until</span>
                            <span className="font-medium text-gray-900">{formatDateTime(user.subscription_end_date)}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-gray-600 text-sm">Days Remaining</span>
                            <span className={`font-medium ${
                              daysRemaining <= 5 ? 'text-red-600 font-bold' : 
                              daysRemaining <= 10 ? 'text-orange-600 font-semibold' : 
                              daysRemaining > 0 ? 'text-green-600' : 'text-red-600'
                            }`}>
                              {daysRemaining > 0 ? `${daysRemaining} days` : daysRemaining === 0 ? 'Expires Today!' : 'Expired'}
                            </span>
                          </div>
                          {daysRemaining <= 5 && daysRemaining > 0 && (
                            <div className="mt-2 p-2 bg-orange-100 rounded-lg">
                              <p className="text-xs text-orange-800 flex items-center gap-1">
                                <FaClock />
                                Subscription expiring soon! User should recharge.
                              </p>
                            </div>
                          )}
                        </>
                      )}
                      {!user.subscription_plan && (
                        <div className="mt-3 p-3 bg-yellow-50 rounded-lg">
                          <p className="text-xs text-yellow-800 flex items-center gap-1">
                            <FaExclamationTriangle />
                            No active subscription plan. User needs to subscribe.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Statistics Section */}
                <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl p-4 border border-green-100">
                  <h4 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <FaChartBar className="mr-2 text-green-600" />
                    User Statistics (All Websites)
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="bg-white p-4 rounded-lg shadow-sm text-center">
                      <FaRobot className="text-blue-600 text-2xl mx-auto mb-2" />
                      <div className="text-2xl font-bold text-gray-900">{user.stats?.total_websites || 0}</div>
                      <div className="text-xs text-gray-600 mt-1">Total Websites</div>
                    </div>
                    <div className="bg-white p-4 rounded-lg shadow-sm text-center">
                      <FaComments className="text-green-600 text-2xl mx-auto mb-2" />
                      <div className="text-2xl font-bold text-gray-900">{user.stats?.total_chat_messages || 0}</div>
                      <div className="text-xs text-gray-600 mt-1">Chat Messages</div>
                    </div>
                    <div className="bg-white p-4 rounded-lg shadow-sm text-center">
                      <FaEnvelopeOpenText className="text-purple-600 text-2xl mx-auto mb-2" />
                      <div className="text-2xl font-bold text-gray-900">{user.stats?.total_contact_forms || 0}</div>
                      <div className="text-xs text-gray-600 mt-1">Contact Forms</div>
                    </div>
                    <div className="bg-white p-4 rounded-lg shadow-sm text-center">
                      <FaFileUpload className="text-yellow-600 text-2xl mx-auto mb-2" />
                      <div className="text-2xl font-bold text-gray-900">{user.stats?.total_uploaded_files || 0}</div>
                      <div className="text-xs text-gray-600 mt-1">Uploaded Files</div>
                    </div>
                  </div>
                </div>

                {/* All Websites Section */}
                {user.websites && user.websites.length > 0 && (
                  <div className="bg-gradient-to-r from-purple-50 to-pink-50 rounded-xl p-4 border border-purple-100">
                    <h3 className="font-semibold text-gray-900 mb-3 flex items-center">
                      <FaRobot className="mr-2 text-purple-600" />
                      User's Websites ({user.websites.length})
                    </h3>
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {user.websites.map((website, index) => (
                        <div key={index} className="bg-white rounded-lg p-4 border border-gray-200 hover:shadow-md transition-shadow">
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <p className="font-semibold text-gray-900">{website.website_name}</p>
                                <span className={`px-2 py-1 text-xs rounded-full ${
                                  website.status === 'active' ? 'bg-green-100 text-green-800' :
                                  website.status === 'training' ? 'bg-yellow-100 text-yellow-800' :
                                  'bg-gray-100 text-gray-800'
                                }`}>
                                  {website.status}
                                </span>
                              </div>
                              <p className="text-sm text-gray-500 break-all">{website.website_url}</p>
                              <p className="text-xs text-gray-400 mt-1">ID: {website.website_id}</p>
                            </div>
                            <div className="flex flex-col items-end gap-2">
                              {website.script_tag && (
                                <button
                                  onClick={() => handleCopyScript(website.website_id, website.script_tag)}
                                  className={`px-2 py-1 text-xs rounded flex items-center gap-1 ${
                                    copiedStates[website.website_id] ? 'bg-green-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                                  }`}
                                >
                                  {copiedStates[website.website_id] ? <FaCheck size={10} /> : <FaCopy size={10} />}
                                  {copiedStates[website.website_id] ? 'Copied!' : 'Copy Script'}
                                </button>
                              )}
                            </div>
                          </div>
                          <div className="flex mt-3 space-x-4 text-xs text-gray-500 border-t pt-3">
                            <span className="flex items-center gap-1">
                              <FaComments className="text-blue-500" /> {website.chat_messages_count || 0} chats
                            </span>
                            <span className="flex items-center gap-1">
                              <FaEnvelope className="text-green-500" /> {website.contact_forms_count || 0} forms
                            </span>
                            <span className="flex items-center gap-1">
                              <FaFileUpload className="text-yellow-500" /> {website.files_count || 0} files
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <FaUserTimes className="text-red-600 text-3xl" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">User not found</h3>
                <p className="text-gray-600">The requested user could not be found</p>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
};

UserDetailsModal.displayName = 'UserDetailsModal';

export default UserDetailsModal;