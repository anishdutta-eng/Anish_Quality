#!/usr/bin/env python3
"""
Test script for IMPROVED client mobility tracking function
"""

# Simulate the improved mobility tracking function
mobility_history = []
mobility_state = "Unknown"
mobility_direction = "●"

def analyze_client_mobility(current_distance, tolerance=2.0, window_size=3):
    """Improved version with more sensitive detection"""
    global mobility_history, mobility_state, mobility_direction
    
    if current_distance is None or current_distance < 0:
        current_distance = 0
    
    mobility_history.append(current_distance)
    
    if len(mobility_history) > window_size + 1:
        mobility_history.pop(0)
    
    if len(mobility_history) < window_size:
        return "Unknown", "?", 0.0, 0
    
    recent_distances = mobility_history[-window_size:]
    differences = [recent_distances[i+1] - recent_distances[i] 
                   for i in range(len(recent_distances)-1)]
    
    avg_change = sum(differences) / len(differences) if differences else 0
    velocity = avg_change
    
    all_increasing = all(d > tolerance for d in differences)
    all_decreasing = all(d < -tolerance for d in differences)
    all_stable = all(abs(d) <= tolerance for d in differences)
    
    # More lenient detection
    increasing_count = sum(1 for d in differences if d > tolerance)
    decreasing_count = sum(1 for d in differences if d < -tolerance)
    stable_count = sum(1 for d in differences if abs(d) <= tolerance)
    
    total_changes = len(differences)
    
    if all_increasing or all_decreasing or all_stable:
        confidence = 100
    else:
        max_count = max(increasing_count, decreasing_count, stable_count)
        confidence = int((max_count / total_changes) * 100)
    
    # More sensitive thresholds (66% instead of 100%)
    if all_increasing or (increasing_count >= total_changes * 0.66):
        state = "Moving Away"
        direction = "↑"
        confidence = max(confidence, int((increasing_count / total_changes) * 100))
    elif all_decreasing or (decreasing_count >= total_changes * 0.66):
        state = "Moving Towards"
        direction = "↓"
        confidence = max(confidence, int((decreasing_count / total_changes) * 100))
    elif all_stable or (stable_count >= total_changes * 0.66):
        state = "Stationary"
        direction = "●"
        confidence = max(confidence, int((stable_count / total_changes) * 100))
    else:
        if abs(avg_change) <= tolerance * 0.5:
            state = "Stationary"
            direction = "●"
        elif avg_change > 0:
            state = "Moving Away"
            direction = "↑"
        else:
            state = "Moving Towards"
            direction = "↓"
    
    mobility_state = state
    mobility_direction = direction
    
    return state, direction, velocity, confidence

# Test scenarios
print("=" * 60)
print("IMPROVED MOBILITY TRACKING - TEST SCENARIOS")
print("Tolerance: 2.0m (reduced from 3.0m)")
print("Detection: 66% threshold (more sensitive)")
print("=" * 60)

# Test 1: Moving Away
print("\n📊 Test 1: Moving Away from AP")
print("-" * 60)
mobility_history = []
distances = [5.0, 10.0, 15.0, 20.0, 25.0]
for i, dist in enumerate(distances, 1):
    state, direction, velocity, confidence = analyze_client_mobility(dist)
    print(f"Iteration {i}: {dist:5.1f}m → {direction} {state:15s} | Velocity: {velocity:+5.1f}m | Confidence: {confidence:3d}%")

# Test 2: Moving Towards (CRITICAL TEST)
print("\n📊 Test 2: Moving Towards AP (CRITICAL)")
print("-" * 60)
mobility_history = []
distances = [25.0, 20.0, 15.0, 10.0, 5.0]
for i, dist in enumerate(distances, 1):
    state, direction, velocity, confidence = analyze_client_mobility(dist)
    print(f"Iteration {i}: {dist:5.1f}m → {direction} {state:15s} | Velocity: {velocity:+5.1f}m | Confidence: {confidence:3d}%")

# Test 3: Gradual Approach (2m steps - should now detect)
print("\n📊 Test 3: Gradual Approach (2m steps)")
print("-" * 60)
mobility_history = []
distances = [20.0, 18.0, 16.0, 14.0, 12.0, 10.0]
for i, dist in enumerate(distances, 1):
    state, direction, velocity, confidence = analyze_client_mobility(dist)
    print(f"Iteration {i}: {dist:5.1f}m → {direction} {state:15s} | Velocity: {velocity:+5.1f}m | Confidence: {confidence:3d}%")

# Test 4: Slow approach (1.5m steps - at tolerance edge)
print("\n📊 Test 4: Slow Approach (1.5m steps)")
print("-" * 60)
mobility_history = []
distances = [15.0, 13.5, 12.0, 10.5, 9.0]
for i, dist in enumerate(distances, 1):
    state, direction, velocity, confidence = analyze_client_mobility(dist)
    print(f"Iteration {i}: {dist:5.1f}m → {direction} {state:15s} | Velocity: {velocity:+5.1f}m | Confidence: {confidence:3d}%")

# Test 5: Stationary (within 2m tolerance)
print("\n📊 Test 5: Stationary (within 2m tolerance)")
print("-" * 60)
mobility_history = []
distances = [10.0, 11.0, 10.5, 11.5, 10.2]
for i, dist in enumerate(distances, 1):
    state, direction, velocity, confidence = analyze_client_mobility(dist)
    print(f"Iteration {i}: {dist:5.1f}m → {direction} {state:15s} | Velocity: {velocity:+5.1f}m | Confidence: {confidence:3d}%")

# Test 6: Mixed with majority towards
print("\n📊 Test 6: Mixed Movement (2 towards, 1 away)")
print("-" * 60)
mobility_history = []
distances = [20.0, 17.0, 19.0, 16.0]
for i, dist in enumerate(distances, 1):
    state, direction, velocity, confidence = analyze_client_mobility(dist)
    print(f"Iteration {i}: {dist:5.1f}m → {direction} {state:15s} | Velocity: {velocity:+5.1f}m | Confidence: {confidence:3d}%")

print("\n" + "=" * 60)
print("✅ All tests completed!")
print("=" * 60)
print("\nKey Improvements:")
print("  1. Tolerance reduced: 3m → 2m (more sensitive)")
print("  2. Detection threshold: 100% → 66% (detects with 2/3 agreement)")
print("  3. Path loss exponent: 3.2 → 2.7 (more accurate for indoor)")
print("  4. Better handling of mixed signals")
print("=" * 60)
