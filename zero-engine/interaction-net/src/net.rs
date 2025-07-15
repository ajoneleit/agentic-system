//! Core InteractionNet implementation

use crate::{Agent, AgentId, AgentType, Edge, EdgeId, Port, Result, InteractionNetError};
use dashmap::DashMap;
use petgraph::graph::{Graph, NodeIndex};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tracing::{debug, trace};

/// The main interaction net structure
#[derive(Clone)]
pub struct InteractionNet {
    /// Graph structure storing agents and edges
    graph: Arc<Graph<Agent, Edge>>,
    
    /// Quick lookup from AgentId to NodeIndex
    agent_lookup: Arc<DashMap<AgentId, NodeIndex>>,
    
    /// Active pairs ready for reduction
    active_pairs: Arc<DashMap<(AgentId, AgentId), ()>>,
    
    /// Port connections
    connections: Arc<DashMap<Port, Port>>,
    
    /// ID generator
    next_id: Arc<AtomicU64>,
}

impl InteractionNet {
    /// Create a new empty interaction net
    pub fn new() -> Self {
        Self {
            graph: Arc::new(Graph::new()),
            agent_lookup: Arc::new(DashMap::new()),
            active_pairs: Arc::new(DashMap::new()),
            connections: Arc::new(DashMap::new()),
            next_id: Arc::new(AtomicU64::new(1)),
        }
    }
    
    /// Generate a new unique agent ID
    pub fn next_agent_id(&self) -> AgentId {
        AgentId(self.next_id.fetch_add(1, Ordering::SeqCst))
    }
    
    /// Add an agent to the net
    pub fn add_agent(&mut self, agent_type: AgentType, arity: usize) -> AgentId {
        let id = self.next_agent_id();
        let agent = Agent::new(id, agent_type, arity);
        
        let graph = Arc::make_mut(&mut self.graph);
        let node_idx = graph.add_node(agent);
        
        self.agent_lookup.insert(id, node_idx);
        
        debug!("Added agent {} with arity {}", id, arity);
        id
    }
    
    /// Connect two ports
    pub fn connect(&mut self, port1: Port, port2: Port) -> Result<()> {
        // Check if ports are already connected
        if self.connections.contains_key(&port1) || self.connections.contains_key(&port2) {
            return Err(InteractionNetError::PortAlreadyConnected);
        }
        
        // Validate ports exist
        if !self.agent_lookup.contains_key(&port1.agent_id) || 
           !self.agent_lookup.contains_key(&port2.agent_id) {
            return Err(InteractionNetError::InvalidConnection(
                "One or both agents do not exist".to_string()
            ));
        }
        
        // Create bidirectional connection
        self.connections.insert(port1, port2);
        self.connections.insert(port2, port1);
        
        // Check if this creates an active pair (principal ports connected)
        if port1.is_principal() && port2.is_principal() {
            self.active_pairs.insert((port1.agent_id, port2.agent_id), ());
            debug!("Created active pair: {} <-> {}", port1.agent_id, port2.agent_id);
        }
        
        Ok(())
    }
    
    /// Get all active pairs
    pub fn get_active_pairs(&self) -> Vec<(AgentId, AgentId)> {
        self.active_pairs
            .iter()
            .map(|entry| *entry.key())
            .collect()
    }
    
    /// Get agent by ID
    pub fn get_agent(&self, id: AgentId) -> Option<Agent> {
        self.agent_lookup
            .get(&id)
            .and_then(|idx| self.graph.node_weight(*idx))
            .cloned()
    }
    
    /// Get connected port
    pub fn get_connected(&self, port: Port) -> Option<Port> {
        self.connections.get(&port).map(|p| *p)
    }
    
    /// Remove an agent and all its connections
    pub fn remove_agent(&mut self, id: AgentId) -> Result<()> {
        let node_idx = self.agent_lookup
            .remove(&id)
            .map(|(_, idx)| idx)
            .ok_or_else(|| InteractionNetError::InvalidConnection(
                format!("Agent {} does not exist", id)
            ))?;
        
        // Remove from graph
        let graph = Arc::make_mut(&mut self.graph);
        let agent = graph.remove_node(node_idx)
            .ok_or_else(|| InteractionNetError::InvalidConnection(
                "Failed to remove agent from graph".to_string()
            ))?;
        
        // Remove all connections to this agent's ports
        for port in agent.all_ports() {
            if let Some(connected) = self.connections.remove(&port) {
                self.connections.remove(&connected.1);
            }
        }
        
        // Remove from active pairs
        self.active_pairs.retain(|pair, _| {
            pair.0 != id && pair.1 != id
        });
        
        Ok(())
    }
    
    /// Get the number of agents
    pub fn agent_count(&self) -> usize {
        self.agent_lookup.len()
    }
    
    /// Get the number of active pairs
    pub fn active_pair_count(&self) -> usize {
        self.active_pairs.len()
    }
    
    /// Check if the net has any active pairs
    pub fn has_active_pairs(&self) -> bool {
        !self.active_pairs.is_empty()
    }
    
    /// Get all agents
    pub fn agents(&self) -> Vec<Agent> {
        self.graph.node_weights().cloned().collect()
    }
    
    /// Clear the net
    pub fn clear(&mut self) {
        Arc::make_mut(&mut self.graph).clear();
        self.agent_lookup.clear();
        self.active_pairs.clear();
        self.connections.clear();
    }
    
    /// Create a subgraph containing specific agents
    pub fn subgraph(&self, agent_ids: &[AgentId]) -> InteractionNet {
        let mut subnet = InteractionNet::new();
        let id_set: HashSet<_> = agent_ids.iter().copied().collect();
        
        // Copy agents
        for id in agent_ids {
            if let Some(agent) = self.get_agent(*id) {
                let new_agent = Agent::new(agent.id, agent.agent_type, agent.arity);
                let graph = Arc::make_mut(&mut subnet.graph);
                let idx = graph.add_node(new_agent);
                subnet.agent_lookup.insert(agent.id, idx);
            }
        }
        
        // Copy connections within the subgraph
        for (port, connected) in self.connections.iter() {
            if id_set.contains(&port.agent_id) && id_set.contains(&connected.agent_id) {
                subnet.connections.insert(*port, *connected);
                
                // Check for active pairs
                if port.is_principal() && connected.is_principal() {
                    subnet.active_pairs.insert((port.agent_id, connected.agent_id), ());
                }
            }
        }
        
        subnet
    }
}

impl Default for InteractionNet {
    fn default() -> Self {
        Self::new()
    }
}

/// Serialization support
#[derive(Serialize, Deserialize)]
struct SerializedNet {
    agents: Vec<Agent>,
    connections: Vec<(Port, Port)>,
}

impl InteractionNet {
    pub fn to_serialized(&self) -> SerializedNet {
        let mut connections = Vec::new();
        let mut seen = HashSet::new();
        
        for entry in self.connections.iter() {
            let (port1, port2) = (*entry.key(), *entry.value());
            let pair = if port1.agent_id.0 < port2.agent_id.0 {
                (port1, port2)
            } else {
                (port2, port1)
            };
            
            if seen.insert(pair) {
                connections.push(pair);
            }
        }
        
        SerializedNet {
            agents: self.agents(),
            connections,
        }
    }
    
    pub fn from_serialized(data: SerializedNet) -> Result<Self> {
        let mut net = InteractionNet::new();
        
        // Add all agents
        for agent in data.agents {
            let graph = Arc::make_mut(&mut net.graph);
            let idx = graph.add_node(agent.clone());
            net.agent_lookup.insert(agent.id, idx);
        }
        
        // Add all connections
        for (port1, port2) in data.connections {
            net.connect(port1, port2)?;
        }
        
        Ok(net)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_net_operations() {
        let mut net = InteractionNet::new();
        
        // Add two agents
        let a1 = net.add_agent(AgentType::Lambda, 3);
        let a2 = net.add_agent(AgentType::Application, 3);
        
        assert_eq!(net.agent_count(), 2);
        
        // Connect principal ports
        let p1 = Port::new(a1, 0);
        let p2 = Port::new(a2, 0);
        
        net.connect(p1, p2).unwrap();
        
        // Should have one active pair
        assert_eq!(net.active_pair_count(), 1);
        assert!(net.has_active_pairs());
        
        // Check connection
        assert_eq!(net.get_connected(p1), Some(p2));
        assert_eq!(net.get_connected(p2), Some(p1));
    }
    
    #[test]
    fn test_agent_removal() {
        let mut net = InteractionNet::new();
        
        let a1 = net.add_agent(AgentType::Lambda, 2);
        let a2 = net.add_agent(AgentType::Application, 2);
        
        net.connect(Port::new(a1, 0), Port::new(a2, 0)).unwrap();
        
        net.remove_agent(a1).unwrap();
        
        assert_eq!(net.agent_count(), 1);
        assert_eq!(net.active_pair_count(), 0);
        assert!(net.get_connected(Port::new(a2, 0)).is_none());
    }
}