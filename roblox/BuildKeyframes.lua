-- Bakes FloatyGroove into a KeyframeSequence you can publish to get an animation ID.
-- 1. Avatar tab > Rig Builder > R15 rig, then select the rig in the Explorer.
-- 2. Paste this whole file into View > Command Bar and press Enter.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Selection = game:GetService("Selection")

local FloatyGroove = require(ReplicatedStorage.FloatyGroove)
local STEPS_PER_BEAT = 8

local rig = Selection:Get()[1]
assert(rig and rig:FindFirstChildOfClass("Humanoid"), "Select an R15 rig first")

local sequence = Instance.new("KeyframeSequence")
sequence.Name = "FloatyGroove"
sequence.Loop = true
sequence.Priority = Enum.AnimationPriority.Action

local steps = FloatyGroove.BEATS * STEPS_PER_BEAT
for i = 0, steps do
	local t = FloatyGroove.LENGTH * i / steps
	local pose = FloatyGroove.pose(t)
	local keyframe = Instance.new("Keyframe")
	keyframe.Time = t

	-- Poses nest like the rig: HumanoidRootPart > LowerTorso > UpperTorso > ...
	local made = {}
	local function getPose(partName)
		if not made[partName] then
			local p = Instance.new("Pose")
			p.Name = partName
			p.CFrame = pose[partName] or CFrame.identity
			local joint = FloatyGroove.JOINTS[partName]
			p.Parent = joint and getPose(joint[2]) or keyframe
			made[partName] = p
		end
		return made[partName]
	end
	for partName in pairs(pose) do
		getPose(partName)
	end

	keyframe.Parent = sequence
end

local saves = rig:FindFirstChild("AnimSaves")
if not saves then
	saves = Instance.new("ObjectValue")
	saves.Name = "AnimSaves"
	saves.Parent = rig
end
sequence.Parent = saves
Selection:Set({ sequence })
print("FloatyGroove saved to " .. sequence:GetFullName())
