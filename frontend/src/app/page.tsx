"use client";

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  Bot, 
  Terminal, 
  LayoutDashboard, 
  GitPullRequest, 
  Settings, 
  Play, 
  Plus, 
  CheckCircle2, 
  CircleDashed,
  Cpu,
  Activity,
  Layers,
  Database
} from 'lucide-react';
import Link from 'next/link';

export default function Dashboard() {
  const [projects, setProjects] = useState([
    { id: '1', name: 'OrbitX Collision Engine', status: 'In Progress', progress: 65, agents: 4 },
    { id: '2', name: 'AegisVault Web App', status: 'Completed', progress: 100, agents: 6 },
  ]);

  const [activeAgents, setActiveAgents] = useState([
    { id: 'a1', role: 'Product Manager', status: 'Thinking', task: 'Writing PRD' },
    { id: 'a2', role: 'System Architect', status: 'Idle', task: 'Waiting for PRD' },
    { id: 'a3', role: 'Senior Developer', status: 'Executing', task: 'Implementing API' },
    { id: 'a4', role: 'QA Engineer', status: 'Idle', task: 'Waiting for deployment' },
  ]);

  return (
    <div className="flex h-screen bg-[#0f1115] text-slate-200 font-sans overflow-hidden">
      {/* Sidebar Navigation */}
      <aside className="w-64 border-r border-slate-800 bg-[#161b22] flex flex-col hidden md:flex">
        <div className="p-6 border-b border-slate-800 flex items-center space-x-3">
          <div className="bg-indigo-500 p-2 rounded-lg">
            <Cpu size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-tight">AI Agency</h1>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
          <NavItem icon={<LayoutDashboard size={20} />} label="Dashboard" active />
          <NavItem icon={<Layers size={20} />} label="Projects" />
          <NavItem icon={<Bot size={20} />} label="Agents Network" />
          <NavItem icon={<Terminal size={20} />} label="Sandbox Logs" />
          <NavItem icon={<Database size={20} />} label="Vector Memory" />
        </nav>
        
        <div className="p-4 border-t border-slate-800">
          <NavItem icon={<Settings size={20} />} label="Settings" />
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full overflow-y-auto">
        {/* Header */}
        <header className="h-20 border-b border-slate-800 bg-[#161b22]/50 backdrop-blur-md sticky top-0 z-10 flex items-center justify-between px-8">
          <div className="flex items-center space-x-2">
            <Activity className="text-indigo-400" size={20} />
            <span className="text-sm font-medium text-slate-400 uppercase tracking-widest">System Status: Online</span>
          </div>
          <button className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md font-medium text-sm flex items-center transition-colors">
            <Plus size={16} className="mr-2" /> New Project
          </button>
        </header>

        {/* Dashboard Content */}
        <div className="p-8 max-w-7xl mx-auto w-full space-y-8">
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <StatCard title="Active Projects" value="2" icon={<Layers className="text-blue-400" />} />
            <StatCard title="Agents Running" value="4" icon={<Bot className="text-emerald-400" />} />
            <StatCard title="Code Commits" value="1,248" icon={<GitPullRequest className="text-purple-400" />} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Projects List */}
            <div className="col-span-2 space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center">
                <LayoutDashboard className="mr-2" size={20} /> Recent Projects
              </h2>
              <div className="bg-[#161b22] border border-slate-800 rounded-xl overflow-hidden shadow-xl">
                {projects.map((project, i) => (
                  <div key={project.id} className={`p-5 flex items-center justify-between ${i !== projects.length - 1 ? 'border-b border-slate-800' : ''} hover:bg-slate-800/50 transition-colors cursor-pointer`}>
                    <div className="flex items-center space-x-4">
                      {project.progress === 100 ? (
                        <CheckCircle2 className="text-emerald-500" size={24} />
                      ) : (
                        <CircleDashed className="text-indigo-500 animate-spin-slow" size={24} />
                      )}
                      <div>
                        <h3 className="font-medium text-slate-100">{project.name}</h3>
                        <p className="text-sm text-slate-500">{project.agents} Agents assigned</p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-6">
                      <div className="text-right">
                        <span className="text-xs font-semibold inline-block text-indigo-400">
                          {project.progress}%
                        </span>
                        <div className="w-32 bg-slate-800 rounded-full h-2 mt-1">
                          <motion.div 
                            initial={{ width: 0 }}
                            animate={{ width: `${project.progress}%` }}
                            transition={{ duration: 1, ease: "easeOut" }}
                            className="bg-indigo-500 h-2 rounded-full"
                          />
                        </div>
                      </div>
                      <button className="text-slate-400 hover:text-white">
                        <Play size={20} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Agent Live Status */}
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center">
                <Bot className="mr-2" size={20} /> Live Agent Status
              </h2>
              <div className="bg-[#161b22] border border-slate-800 rounded-xl p-5 space-y-4 shadow-xl">
                {activeAgents.map(agent => (
                  <div key={agent.id} className="flex items-start space-x-3 p-3 rounded-lg bg-[#0f1115] border border-slate-800/60">
                    <div className={`mt-1 h-2 w-2 rounded-full ${
                      agent.status === 'Executing' ? 'bg-emerald-500 animate-pulse' :
                      agent.status === 'Thinking' ? 'bg-amber-500 animate-pulse' : 'bg-slate-600'
                    }`} />
                    <div>
                      <p className="text-sm font-medium text-slate-200">{agent.role}</p>
                      <p className="text-xs text-slate-400 mt-1">
                        <span className={
                          agent.status === 'Executing' ? 'text-emerald-400' :
                          agent.status === 'Thinking' ? 'text-amber-400' : 'text-slate-500'
                        }>[{agent.status}]</span> - {agent.task}
                      </p>
                    </div>
                  </div>
                ))}
                <button className="w-full mt-4 py-2 text-sm text-indigo-400 border border-indigo-500/30 rounded-lg hover:bg-indigo-500/10 transition-colors">
                  View Network Topology
                </button>
              </div>
            </div>
          </div>
          
        </div>
      </main>
    </div>
  );
}

function NavItem({ icon, label, active = false }: { icon: React.ReactNode, label: string, active?: boolean }) {
  return (
    <Link href="#" className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all duration-200 ${
      active ? 'bg-indigo-600/10 text-indigo-400 border border-indigo-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
    }`}>
      {icon}
      <span className="font-medium text-sm">{label}</span>
    </Link>
  );
}

function StatCard({ title, value, icon }: { title: string, value: string, icon: React.ReactNode }) {
  return (
    <div className="bg-[#161b22] border border-slate-800 rounded-xl p-6 flex items-center justify-between shadow-xl">
      <div>
        <p className="text-sm text-slate-400 font-medium">{title}</p>
        <p className="text-3xl font-bold text-white mt-2">{value}</p>
      </div>
      <div className="p-3 bg-[#0f1115] rounded-lg border border-slate-800">
        {icon}
      </div>
    </div>
  );
}
