//! Interaction Net - Core computational model for /zero
//! 
//! Implements a parallel graph rewriting system based on Lafont's interaction nets,
//! supporting optimal lambda calculus reduction and geometric evolution.

use dashmap::DashMap;
use petgraph::graph::{Graph, NodeIndex};
use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use thiserror::Error;

pub mod agent;
pub mod edge;
pub mod net;
pub mod reduction;
pub mod rewrite;

pub use agent::{Agent, AgentId, AgentType, Port};
pub use edge::{Edge, EdgeId};
pub use net::InteractionNet;
pub use reduction::{ReductionResult, ReductionStrategy};
pub use rewrite::{RewriteRule, RuleSet};

#[derive(Error, Debug)]
pub enum InteractionNetError {
    #[error("Invalid agent connection: {0}")]
    InvalidConnection(String),
    
    #[error("No matching rewrite rule for pair: {0:?}")]
    NoRewriteRule((AgentType, AgentType)),
    
    #[error("Cyclic dependency detected")]
    CyclicDependency,
    
    #[error("Port already connected")]
    PortAlreadyConnected,
}

/// Result type for interaction net operations
pub type Result<T> = std::result::Result<T, InteractionNetError>;

/// Trait for types that can be encoded as interaction nets
pub trait IntoInteractionNet {
    fn into_net(self) -> Result<InteractionNet>;
}

/// Trait for types that can be decoded from interaction nets
pub trait FromInteractionNet: Sized {
    fn from_net(net: &InteractionNet) -> Result<Self>;
}

/// Configuration for interaction net behavior
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetConfig {
    /// Maximum parallel reduction threads
    pub max_parallel_threads: usize,
    
    /// Enable geometric evolution
    pub enable_evolution: bool,
    
    /// Evolution fitness function
    pub fitness_metric: FitnessMetric,
    
    /// Reduction strategy
    pub reduction_strategy: ReductionStrategy,
}

impl Default for NetConfig {
    fn default() -> Self {
        Self {
            max_parallel_threads: num_cpus::get(),
            enable_evolution: true,
            fitness_metric: FitnessMetric::ReductionSteps,
            reduction_strategy: ReductionStrategy::Parallel,
        }
    }
}

/// Fitness metrics for geometric evolution
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum FitnessMetric {
    /// Minimize reduction steps
    ReductionSteps,
    
    /// Minimize memory usage
    MemoryUsage,
    
    /// Maximize parallelism
    Parallelism,
    
    /// Custom fitness function
    Custom,
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_net_creation() {
        let net = InteractionNet::new();
        assert_eq!(net.agent_count(), 0);
        assert_eq!(net.active_pair_count(), 0);
    }
}