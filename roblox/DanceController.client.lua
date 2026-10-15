-- Press G to start/stop FloatyGroove. Walking, jumping or dying stops it.
-- LocalScript: put it in StarterPlayer > StarterCharacterScripts.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local FloatyGroove = require(ReplicatedStorage:WaitForChild("FloatyGroove"))

-- Paste the ID you get from publishing the animation (see README) so other
-- players see the dance. Left empty, the dance is driven from code and only
-- you see it (Motor6D.Transform doesn't replicate).
local ANIMATION_ID = ""
local TOGGLE_KEY = Enum.KeyCode.G

local character = script.Parent
local humanoid = character:WaitForChild("Humanoid")
local animator = humanoid:WaitForChild("Animator")

if humanoid.RigType ~= Enum.HumanoidRigType.R15 then
	warn("FloatyGroove needs an R15 character")
	return
end

local track
if ANIMATION_ID ~= "" then
	local animation = Instance.new("Animation")
	animation.AnimationId = "rbxassetid://" .. ANIMATION_ID
	track = animator:LoadAnimation(animation)
	track.Looped = true
	track.Priority = Enum.AnimationPriority.Action
end

local motors = {} -- Motor6D -> part name
for partName, joint in pairs(FloatyGroove.JOINTS) do
	motors[character:WaitForChild(partName):WaitForChild(joint[1])] = partName
end

local dancing = false
local connection

local function stop()
	if not dancing then
		return
	end
	dancing = false
	if track then
		track:Stop(0.2)
	else
		connection:Disconnect()
		for motor in pairs(motors) do
			motor.Transform = CFrame.identity
		end
	end
end

local function start()
	if dancing or humanoid.Health <= 0 then
		return
	end
	dancing = true
	if track then
		track:Play(0.2)
	else
		local startTime = os.clock()
		-- PreSimulation runs after the Animator, so this overrides the idle pose
		connection = RunService.PreSimulation:Connect(function()
			local pose = FloatyGroove.pose(os.clock() - startTime)
			for motor, partName in pairs(motors) do
				motor.Transform = pose[partName]
			end
		end)
	end
end

UserInputService.InputBegan:Connect(function(input, gameProcessed)
	if gameProcessed or input.KeyCode ~= TOGGLE_KEY then
		return
	end
	if dancing then
		stop()
	else
		start()
	end
end)

humanoid:GetPropertyChangedSignal("MoveDirection"):Connect(function()
	if humanoid.MoveDirection.Magnitude > 0 then
		stop()
	end
end)
humanoid.Jumping:Connect(stop)
humanoid.Died:Connect(stop)
