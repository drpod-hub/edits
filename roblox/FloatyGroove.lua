-- FloatyGroove: an 8-beat R15 dance loop. Knees bounce on every beat, arms
-- pump in turn, then the last two beats are a spin with arms out.
-- ModuleScript: put it in ReplicatedStorage, named "FloatyGroove".

local FloatyGroove = {}

FloatyGroove.BPM = 120
FloatyGroove.BEATS = 8
FloatyGroove.LENGTH = FloatyGroove.BEATS * 60 / FloatyGroove.BPM -- seconds

-- part name -> { Motor6D name, parent part name }
FloatyGroove.JOINTS = {
	LowerTorso = { "Root", "HumanoidRootPart" },
	UpperTorso = { "Waist", "LowerTorso" },
	Head = { "Neck", "UpperTorso" },
	LeftUpperArm = { "LeftShoulder", "UpperTorso" },
	LeftLowerArm = { "LeftElbow", "LeftUpperArm" },
	LeftHand = { "LeftWrist", "LeftLowerArm" },
	RightUpperArm = { "RightShoulder", "UpperTorso" },
	RightLowerArm = { "RightElbow", "RightUpperArm" },
	RightHand = { "RightWrist", "RightLowerArm" },
	LeftUpperLeg = { "LeftHip", "LowerTorso" },
	LeftLowerLeg = { "LeftKnee", "LeftUpperLeg" },
	LeftFoot = { "LeftAnkle", "LeftLowerLeg" },
	RightUpperLeg = { "RightHip", "LowerTorso" },
	RightLowerLeg = { "RightKnee", "RightUpperLeg" },
	RightFoot = { "RightAnkle", "RightLowerLeg" },
}

local TAU = 2 * math.pi
local angles = CFrame.Angles

local function smoothstep(x)
	x = math.clamp(x, 0, 1)
	return x * x * (3 - 2 * x)
end

-- Returns { [part name] = Motor6D.Transform } at time t (seconds); loops every LENGTH.
function FloatyGroove.pose(t)
	local b = (t * FloatyGroove.BPM / 60) % FloatyGroove.BEATS
	local dip = (1 + math.cos(TAU * b)) / 2 -- 1 on the beat, 0 between beats
	local sway = math.sin(math.pi * b) -- side to side every 2 beats
	local pump = (1 + sway) / 2 -- right arm up while left is down, then swap
	local spin = smoothstep((b - 6) / 2) -- 0 -> 1 over beats 6-8
	local armsOut = math.sin(math.pi * spin)

	local p = {}
	p.LowerTorso = CFrame.new(0.15 * sway, -0.2 * dip, 0) * angles(0, TAU * spin, 0.1 * sway)
	p.UpperTorso = angles(0.1 * dip, 0.25 * sway, -0.08 * sway)
	p.Head = angles(-0.18 * dip, -0.2 * sway, 0)

	for _, arm in ipairs({ { "Right", 1, pump }, { "Left", -1, 1 - pump } }) do
		local side, dir, up = arm[1], arm[2], arm[3]
		local pumping = angles(0.3 + 2.4 * up, 0, 0.25 * dir)
		local tPose = angles(0, 0, 1.5 * dir)
		p[side .. "UpperArm"] = pumping:Lerp(tPose, armsOut)
		p[side .. "LowerArm"] = angles((0.3 + 1.2 * (1 - up)) * (1 - armsOut), 0, 0)
		p[side .. "Hand"] = angles(0.3 * dip, 0, 0)
	end

	-- hip + knee + ankle sum to zero so the feet stay flat while the knees bend
	for _, side in ipairs({ "Left", "Right" }) do
		p[side .. "UpperLeg"] = angles(0.5 * dip, 0, 0)
		p[side .. "LowerLeg"] = angles(-1.0 * dip, 0, 0)
		p[side .. "Foot"] = angles(0.5 * dip, 0, 0)
	end

	return p
end

return FloatyGroove
