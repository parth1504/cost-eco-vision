import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import {
  BarChart3,
  Shield,
  AlertTriangle,
  Server,
  DollarSign,
  Settings,
  ChevronLeft,
  Cloud,
  Menu
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const navigation = [
  { name: "Overview", href: "/", icon: BarChart3 },
  { name: "Alerts", href: "/alerts", icon: AlertTriangle },
  { name: "Resources", href: "/resources", icon: Server },
  { name: "Cost Optimization", href: "/cost-optimization", icon: DollarSign },
  { name: "Security", href: "/security", icon: Shield },
  { name: "Settings", href: "/settings", icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation();

  return (
    <motion.div
      initial={false}
      animate={{ width: collapsed ? 80 : 280 }}
      transition={{ duration: 0.3, ease: "easeInOut" }}
      className="bg-sidebar border-r border-sidebar-border flex flex-col h-full"
    >
      {/* Header */}
      <div className="p-4 border-b border-sidebar-border">
        <div className="flex items-center justify-between">
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center space-x-3"
            >
              <div className="bg-primary p-2 rounded-lg">
                <Cloud className="h-6 w-6 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-sidebar-foreground">CloudOps</h1>
                <p className="text-xs text-sidebar-foreground/60">AI Agent Dashboard</p>
              </div>
            </motion.div>
          )}
          
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggle}
            className="h-8 w-8 p-0 text-sidebar-foreground hover:bg-sidebar-accent ml-auto"
          >
            {collapsed ? (
              <Menu className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <div className="space-y-2">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            
            return (
              <NavLink
                key={item.name}
                to={item.href}
                className={cn(
                  "flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 group",
                  isActive
                    ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"
                    : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                )}
              >
                <item.icon className={cn(
                  "h-5 w-5 flex-shrink-0",
                  collapsed ? "mx-auto" : "mr-3"
                )} />
                
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -10 }}
                    transition={{ duration: 0.2 }}
                  >
                    {item.name}
                  </motion.span>
                )}
                
                {/* Active indicator */}
                {isActive && collapsed && (
                  <motion.div
                    layoutId="sidebar-indicator"
                    className="absolute left-0 w-1 h-8 bg-sidebar-primary rounded-r-full"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
              </NavLink>
            );
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-sidebar-border">
        <div className={cn(
          "flex items-center",
          collapsed ? "justify-center" : "space-x-3"
        )}>
          <div className="h-8 w-8 bg-success/10 rounded-full flex items-center justify-center">
            <div className="h-2 w-2 bg-success rounded-full"></div>
          </div>
          
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1"
            >
              <p className="text-sm font-medium text-sidebar-foreground">Agent Active</p>
              <p className="text-xs text-sidebar-foreground/60">24/7 Monitoring</p>
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}