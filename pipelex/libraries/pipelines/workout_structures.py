from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """Information about the user including fitness level, goals, and available equipment."""
    name: str = Field(description="User's name")
    age: int = Field(description="User's age")
    height: str = Field(description="User's height")
    weight: str = Field(description="User's weight")
    fitness_level: str = Field(description="Current fitness level (beginner, intermediate, advanced)")
    goals: List[str] = Field(description="User's fitness goals")
    limitations: Optional[List[str]] = Field(default=None, description="Any physical limitations or medical conditions")
    available_equipment: List[str] = Field(description="Equipment the user has access to")
    preferred_workout_duration: str = Field(description="Preferred duration of workout sessions")
    workout_frequency: int = Field(description="Number of days per week the user can work out")


class FitnessAssessment(BaseModel):
    """Evaluation of the user's current fitness capabilities and appropriate workout intensity."""
    fitness_level: str = Field(description="Determined fitness level (beginner, intermediate, advanced)")
    recommended_intensity: str = Field(description="Recommended workout intensity range")
    focus_areas: List[str] = Field(description="Key areas to focus on based on goals")
    exercise_modifications: Optional[List[str]] = Field(default=None, description="Necessary exercise modifications")
    recommended_frequency: str = Field(description="Recommended workout frequency")
    notes: Optional[str] = Field(default=None, description="Additional assessment notes")


class WorkoutComponent(BaseModel):
    """A specific part of a workout routine (warm-up, exercise set, cool-down)."""
    component_type: str = Field(description="Type of component (warm-up, main, cool-down)")
    duration: str = Field(description="Estimated duration of this component")
    exercises: List[Dict[str, str]] = Field(description="List of exercises with details")
    instructions: str = Field(description="General instructions for this component")
    intensity_level: str = Field(description="Intensity level of this component")


class WorkoutPlan(BaseModel):
    """A complete personalized workout plan with detailed instructions."""
    title: str = Field(description="Title of the workout plan")
    description: str = Field(description="Overall description of the workout plan")
    fitness_level: str = Field(description="Target fitness level")
    total_duration: str = Field(description="Total workout duration")
    equipment_needed: List[str] = Field(description="Required equipment")
    warm_up: Optional[WorkoutComponent] = Field(default=None, description="Warm-up component")
    main_workout: Optional[WorkoutComponent] = Field(default=None, description="Main workout component")
    cool_down: Optional[WorkoutComponent] = Field(default=None, description="Cool-down component")
    progression_tips: Optional[List[str]] = Field(default=None, description="Tips for progression")
    schedule: Optional[Dict[str, str]] = Field(default=None, description="Recommended weekly schedule")
    nutrition_tips: Optional[List[str]] = Field(default=None, description="Complementary nutrition suggestions")
    safety_considerations: Optional[List[str]] = Field(default=None, description="Safety tips and form considerations")
    tracking_methods: Optional[List[str]] = Field(default=None, description="Suggested progress tracking methods") 