/**
 * Generic Placeholder Page Component
 * Used for routes not yet fully implemented
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';

export default function PlaceholderPage({ title, description, icon }) {
  const navigate = useNavigate();

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 text-blue-600 hover:underline text-sm"
      >
        ← Back
      </button>
      
      <div className="bg-white rounded-lg shadow p-12 text-center">
        <div className="text-6xl mb-4">{icon}</div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">{title}</h1>
        <p className="text-gray-600 mb-8">{description}</p>
        
        <div className="bg-blue-50 border border-blue-200 rounded p-4">
          <p className="text-sm text-blue-800">
            ⚙️ This page is under development.
          </p>
          <p className="text-xs text-blue-700 mt-1">
            Check back soon for full functionality!
          </p>
        </div>
      </div>
    </div>
  );
}
