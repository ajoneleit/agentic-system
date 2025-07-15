//! Edge definitions for interaction nets

use serde::{Deserialize, Serialize};
use std::fmt;

use crate::{AgentId, Port};

/// Unique identifier for edges
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct EdgeId(pub u64);

impl fmt::Display for EdgeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Edge{}", self.0)
    }
}

/// Edge connecting two ports in an interaction net
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Edge {
    pub id: EdgeId,
    pub source: Port,
    pub target: Port,
    pub edge_type: EdgeType,
}

impl Edge {
    pub fn new(id: EdgeId, source: Port, target: Port) -> Self {
        let edge_type = if source.is_principal() && target.is_principal() {
            EdgeType::Active
        } else {
            EdgeType::Normal
        };
        
        Self {
            id,
            source,
            target,
            edge_type,
        }
    }
    
    /// Check if this edge forms an active pair
    pub fn is_active(&self) -> bool {
        matches!(self.edge_type, EdgeType::Active)
    }
    
    /// Get the agents connected by this edge
    pub fn agents(&self) -> (AgentId, AgentId) {
        (self.source.agent_id, self.target.agent_id)
    }
}

/// Type of edge in the interaction net
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EdgeType {
    /// Normal edge between ports
    Normal,
    
    /// Active edge between principal ports
    Active,
    
    /// Virtual edge (for visualization)
    Virtual,
}