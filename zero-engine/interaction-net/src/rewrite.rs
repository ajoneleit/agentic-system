//! Rewrite rules for interaction nets

use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

use crate::{AgentType, InteractionNet, Result};

/// A rewrite rule for interaction nets
#[derive(Clone)]
pub struct RewriteRule {
    /// Pattern to match (pair of agent types)
    pub pattern: (AgentType, AgentType),
    
    /// Function that generates the replacement net
    pub replacement: Arc<dyn Fn() -> Result<InteractionNet> + Send + Sync>,
    
    /// Rule metadata
    pub metadata: RuleMetadata,
}

impl RewriteRule {
    pub fn new(
        pattern: (AgentType, AgentType),
        replacement: impl Fn() -> Result<InteractionNet> + Send + Sync + 'static,
        metadata: RuleMetadata,
    ) -> Self {
        Self {
            pattern,
            replacement: Arc::new(replacement),
            metadata,
        }
    }
    
    /// Apply this rule to generate a replacement net
    pub fn apply(&self) -> Result<InteractionNet> {
        (self.replacement)()
    }
}

/// Metadata about a rewrite rule
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuleMetadata {
    pub name: String,
    pub description: String,
    pub priority: i32,
    pub cost: f64,
}

impl Default for RuleMetadata {
    fn default() -> Self {
        Self {
            name: "unnamed".to_string(),
            description: "".to_string(),
            priority: 0,
            cost: 1.0,
        }
    }
}

/// Collection of rewrite rules
pub struct RuleSet {
    rules: DashMap<(AgentType, AgentType), Vec<RewriteRule>>,
}

impl RuleSet {
    pub fn new() -> Self {
        Self {
            rules: DashMap::new(),
        }
    }
    
    /// Add a rewrite rule
    pub fn add_rule(&self, rule: RewriteRule) {
        self.rules
            .entry(rule.pattern.clone())
            .or_insert_with(Vec::new)
            .push(rule);
    }
    
    /// Get matching rules for a pair of agent types
    pub fn get_rules(&self, pattern: &(AgentType, AgentType)) -> Option<Vec<RewriteRule>> {
        self.rules.get(pattern).map(|rules| rules.clone())
    }
    
    /// Get the highest priority rule for a pattern
    pub fn get_best_rule(&self, pattern: &(AgentType, AgentType)) -> Option<RewriteRule> {
        self.rules
            .get(pattern)
            .and_then(|rules| {
                rules
                    .iter()
                    .max_by_key(|r| r.metadata.priority)
                    .cloned()
            })
    }
    
    /// Load standard rewrite rules
    pub fn load_standard_rules(&self) {
        use AgentType::*;
        
        // Lambda-Application rule (β-reduction)
        self.add_rule(RewriteRule::new(
            (Lambda, Application),
            || {
                let mut net = InteractionNet::new();
                // Implementation of β-reduction
                // This would create the appropriate net structure
                Ok(net)
            },
            RuleMetadata {
                name: "beta-reduction".to_string(),
                description: "Lambda application".to_string(),
                priority: 10,
                cost: 1.0,
            },
        ));
        
        // Duplicator rules
        self.add_rule(RewriteRule::new(
            (Duplicator, Lambda),
            || {
                let mut net = InteractionNet::new();
                // Implementation of duplication
                Ok(net)
            },
            RuleMetadata {
                name: "duplicate-lambda".to_string(),
                description: "Duplicate a lambda".to_string(),
                priority: 5,
                cost: 2.0,
            },
        ));
        
        // Eraser rules
        self.add_rule(RewriteRule::new(
            (Eraser, Lambda),
            || {
                // Erasing returns empty net
                Ok(InteractionNet::new())
            },
            RuleMetadata {
                name: "erase-lambda".to_string(),
                description: "Erase a lambda".to_string(),
                priority: 5,
                cost: 0.5,
            },
        ));
    }
}

impl Default for RuleSet {
    fn default() -> Self {
        let set = Self::new();
        set.load_standard_rules();
        set
    }
}

/// Builder for creating custom rewrite rules
pub struct RuleBuilder {
    pattern: Option<(AgentType, AgentType)>,
    metadata: RuleMetadata,
}

impl RuleBuilder {
    pub fn new() -> Self {
        Self {
            pattern: None,
            metadata: RuleMetadata::default(),
        }
    }
    
    pub fn pattern(mut self, left: AgentType, right: AgentType) -> Self {
        self.pattern = Some((left, right));
        self
    }
    
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.metadata.name = name.into();
        self
    }
    
    pub fn description(mut self, desc: impl Into<String>) -> Self {
        self.metadata.description = desc.into();
        self
    }
    
    pub fn priority(mut self, priority: i32) -> Self {
        self.metadata.priority = priority;
        self
    }
    
    pub fn cost(mut self, cost: f64) -> Self {
        self.metadata.cost = cost;
        self
    }
    
    pub fn build<F>(self, replacement: F) -> Result<RewriteRule>
    where
        F: Fn() -> Result<InteractionNet> + Send + Sync + 'static,
    {
        let pattern = self.pattern.ok_or_else(|| {
            crate::InteractionNetError::InvalidConnection("Rule pattern not specified".to_string())
        })?;
        
        Ok(RewriteRule::new(pattern, replacement, self.metadata))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_rule_builder() {
        let rule = RuleBuilder::new()
            .pattern(AgentType::Lambda, AgentType::Application)
            .name("test-rule")
            .priority(5)
            .build(|| Ok(InteractionNet::new()))
            .unwrap();
        
        assert_eq!(rule.pattern, (AgentType::Lambda, AgentType::Application));
        assert_eq!(rule.metadata.name, "test-rule");
        assert_eq!(rule.metadata.priority, 5);
    }
    
    #[test]
    fn test_rule_set() {
        let rules = RuleSet::new();
        
        let rule = RewriteRule::new(
            (AgentType::Lambda, AgentType::Application),
            || Ok(InteractionNet::new()),
            RuleMetadata::default(),
        );
        
        rules.add_rule(rule);
        
        let found = rules.get_rules(&(AgentType::Lambda, AgentType::Application));
        assert!(found.is_some());
        assert_eq!(found.unwrap().len(), 1);
    }
}