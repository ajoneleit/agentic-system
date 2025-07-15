//! Reduction strategies and results for interaction nets

use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::{AgentId, InteractionNet};

/// Strategy for reducing interaction nets
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub enum ReductionStrategy {
    /// Sequential reduction (one active pair at a time)
    Sequential,
    
    /// Parallel reduction (all independent pairs simultaneously)
    Parallel,
    
    /// Lazy reduction (only reduce when needed)
    Lazy,
    
    /// Optimal reduction (Lamping's algorithm)
    Optimal,
}

/// Result of a reduction step
#[derive(Debug, Clone)]
pub struct ReductionResult {
    /// Active pair that was reduced
    pub active_pair: (AgentId, AgentId),
    
    /// Number of new agents created
    pub agents_created: usize,
    
    /// Number of agents removed
    pub agents_removed: usize,
    
    /// New active pairs created
    pub new_active_pairs: Vec<(AgentId, AgentId)>,
    
    /// Time taken for reduction
    pub duration: Duration,
    
    /// Whether reduction succeeded
    pub success: bool,
    
    /// Error message if failed
    pub error: Option<String>,
}

impl ReductionResult {
    pub fn success(
        active_pair: (AgentId, AgentId),
        agents_created: usize,
        agents_removed: usize,
        new_active_pairs: Vec<(AgentId, AgentId)>,
        duration: Duration,
    ) -> Self {
        Self {
            active_pair,
            agents_created,
            agents_removed,
            new_active_pairs,
            duration,
            success: true,
            error: None,
        }
    }
    
    pub fn failure(active_pair: (AgentId, AgentId), error: String) -> Self {
        Self {
            active_pair,
            agents_created: 0,
            agents_removed: 0,
            new_active_pairs: vec![],
            duration: Duration::default(),
            success: false,
            error: Some(error),
        }
    }
}

/// Statistics about a reduction sequence
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReductionStats {
    /// Total reduction steps
    pub total_steps: usize,
    
    /// Successful reductions
    pub successful_steps: usize,
    
    /// Failed reductions
    pub failed_steps: usize,
    
    /// Total duration
    pub total_duration: Duration,
    
    /// Maximum parallelism achieved
    pub max_parallelism: usize,
    
    /// Average step duration
    pub avg_step_duration: Duration,
}

impl ReductionStats {
    pub fn new() -> Self {
        Self {
            total_steps: 0,
            successful_steps: 0,
            failed_steps: 0,
            total_duration: Duration::default(),
            max_parallelism: 0,
            avg_step_duration: Duration::default(),
        }
    }
    
    pub fn update(&mut self, result: &ReductionResult, parallelism: usize) {
        self.total_steps += 1;
        
        if result.success {
            self.successful_steps += 1;
        } else {
            self.failed_steps += 1;
        }
        
        self.total_duration += result.duration;
        self.max_parallelism = self.max_parallelism.max(parallelism);
        
        if self.total_steps > 0 {
            self.avg_step_duration = self.total_duration / self.total_steps as u32;
        }
    }
}

/// Trait for reducible structures
pub trait Reducible {
    /// Perform one reduction step
    fn reduce_step(&mut self) -> ReductionResult;
    
    /// Reduce to normal form
    fn reduce_to_normal_form(&mut self) -> ReductionStats;
    
    /// Check if in normal form (no active pairs)
    fn is_normal_form(&self) -> bool;
}