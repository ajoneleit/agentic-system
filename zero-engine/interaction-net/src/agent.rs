//! Agent definitions for interaction nets

use serde::{Deserialize, Serialize};
use std::fmt;

/// Unique identifier for agents
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AgentId(pub u64);

impl fmt::Display for AgentId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Agent{}", self.0)
    }
}

/// Types of agents in the interaction net
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AgentType {
    /// Lambda abstraction
    Lambda,
    
    /// Application
    Application,
    
    /// Duplicator (for optimal reduction)
    Duplicator,
    
    /// Eraser (for garbage collection)
    Eraser,
    
    /// Custom agent type for domain-specific nets
    Custom(String),
}

impl fmt::Display for AgentType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AgentType::Lambda => write!(f, "λ"),
            AgentType::Application => write!(f, "@"),
            AgentType::Duplicator => write!(f, "δ"),
            AgentType::Eraser => write!(f, "ε"),
            AgentType::Custom(name) => write!(f, "{}", name),
        }
    }
}

/// Port on an agent for connections
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Port {
    pub agent_id: AgentId,
    pub port_index: usize,
}

impl Port {
    pub fn new(agent_id: AgentId, port_index: usize) -> Self {
        Self { agent_id, port_index }
    }
    
    pub fn is_principal(&self) -> bool {
        self.port_index == 0
    }
}

/// Agent in an interaction net
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Agent {
    pub id: AgentId,
    pub agent_type: AgentType,
    pub arity: usize,
    pub metadata: Option<AgentMetadata>,
}

impl Agent {
    pub fn new(id: AgentId, agent_type: AgentType, arity: usize) -> Self {
        Self {
            id,
            agent_type,
            arity,
            metadata: None,
        }
    }
    
    pub fn with_metadata(mut self, metadata: AgentMetadata) -> Self {
        self.metadata = Some(metadata);
        self
    }
    
    pub fn principal_port(&self) -> Port {
        Port::new(self.id, 0)
    }
    
    pub fn auxiliary_ports(&self) -> Vec<Port> {
        (1..self.arity)
            .map(|i| Port::new(self.id, i))
            .collect()
    }
    
    pub fn all_ports(&self) -> Vec<Port> {
        (0..self.arity)
            .map(|i| Port::new(self.id, i))
            .collect()
    }
}

/// Metadata associated with agents
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMetadata {
    pub label: Option<String>,
    pub position: Option<(f64, f64)>,
    pub color: Option<String>,
    pub properties: HashMap<String, serde_json::Value>,
}

impl Default for AgentMetadata {
    fn default() -> Self {
        Self {
            label: None,
            position: None,
            color: None,
            properties: HashMap::new(),
        }
    }
}

use std::collections::HashMap;

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_agent_creation() {
        let agent = Agent::new(
            AgentId(1),
            AgentType::Lambda,
            3, // 1 principal + 2 auxiliary
        );
        
        assert_eq!(agent.id, AgentId(1));
        assert_eq!(agent.arity, 3);
        assert_eq!(agent.principal_port(), Port::new(AgentId(1), 0));
        assert_eq!(agent.auxiliary_ports().len(), 2);
    }
    
    #[test]
    fn test_port_principal_check() {
        let port = Port::new(AgentId(1), 0);
        assert!(port.is_principal());
        
        let aux_port = Port::new(AgentId(1), 1);
        assert!(!aux_port.is_principal());
    }
}