import asyncio
from platform import machine
import sys
import logging
logging.basicConfig(level=logging.INFO)

from viam.components.gripper import Gripper
from viam.components.arm import Arm, JointPositions
from viam.proto.component.arm import MoveOptions
from viam.services.vision import VisionClient

from connect import connect


""" Unfortunately this involves me hard coding the ending bounds of the arm
If this was a real project I would try to write a function that finds the bounds of the joints
agnostic of the arm"""
SO_101_JOINT_0_MIN_DEG = -90 #right
SO_101_JOINT_0_MAX_DEG = 0 #left
SO_101_JOINT_0_INCREMENT = 10
SO_101_JOINT_2_MIN_DEG = -95
SO_101_JOINT_2_MAX_DEG = 55 # This can actually be more but then it would hit the table



class Greeter:
    def __init__(self, robot):
        self.robot = robot
        self.arm = Arm.from_robot(robot, "so101-arm")
        self.gripper = Gripper.from_robot(robot, "so101-gripper")
        self.vision_service = VisionClient.from_robot(self.robot, "vision-1")
        self.direction = "left"
        self.giving_attention = False
        self.slow = MoveOptions(max_vel_degs_per_sec=20, max_acc_degs_per_sec2=60)
        self.fast = MoveOptions(max_vel_degs_per_sec=80, max_acc_degs_per_sec2=60)

    async def _move(self, joints, speed = "fast"):
        if speed == "slow": 
            await self.arm.move_through_joint_positions([JointPositions(values=joints)], self.slow)
        else:
            await self.arm.move_to_joint_positions(JointPositions(values=joints))
        # Some arm drivers return before the motion finishes, so wait for it here
        await asyncio.sleep(0.1)  # give the arm time to report that it's moving
        while await self.arm.is_moving():
            await asyncio.sleep(0.05)

    async def wave(self):
        joints = list((await self.arm.get_joint_positions()).values)
        original_joint_three = joints[3]
        logging.info("starting wave")

        joints[3] = joints[3] + 30
        await self._move(joints)
        joints[3] = original_joint_three
        await self._move(joints)
        joints[3] = joints[3] + 30
        await self._move(joints)
        joints[3] = original_joint_three
        await self._move(joints)



    async def zero(self):
        """Zero out all the joints, returning the arm to a neutral position."""
        await self.arm.move_to_joint_positions(
            JointPositions(values=[0.00, -13.80, -77.89, -73.32, -0.18])
        )

    async def find_person(self):
        """Use the vision service to find a person and then wave at them.
        This function will wave at everyone in the cameras view which means if 
        there are a ton of people the camera might get behind and the waves wouldn't 
        be that accurate"""
        while True:
            detections = await self.vision_service.get_detections_from_camera("camera-1")
            for d in detections:
                if d.class_name == "Person" and d.confidence > 0.75:
                    logging.info("Person detected: %s, Confidence: %f", d.class_name, d.confidence)
                    self.giving_attention = True
                    await asyncio.sleep(2)
                    await self.wave()
                    logging.info("finished wave")
                    await self.sway_step(2)
                    logging.info("finished step 2")
                    self.giving_attention = False
            if self.giving_attention == False:
                await self.sway_step()




    async def run(self):
        await self.find_person()


    async def sway(self):
        while True:
            await self.sway_step()
        # joints = list((await self.arm.get_joint_positions()).values)
        # while True:     
        #     #left           
        #     joints[0] = SO_101_JOINT_0_MIN_DEG
        #     await self.arm.move_to_joint_positions(JointPositions(values=joints))
        #     #right
        #     joints[0] = SO_101_JOINT_0_MAX_DEG
        #     await self.arm.move_to_joint_positions(JointPositions(values=joints))


    async def thumbs_down(self):
        await self.gripper.open()
        await asyncio.sleep(3)
        await self.gripper.grab()

    async def sway_step(self, multiplier = 1):
        logging.info("starting step")
        joints = list((await self.arm.get_joint_positions()).values)

        turning_joint = joints[0]
        if self.direction == "left":
            turning_joint = turning_joint + (SO_101_JOINT_0_INCREMENT * multiplier)
            if turning_joint >= SO_101_JOINT_0_MAX_DEG:
                self.direction = "right"
            else:  
                joints[0] = turning_joint          
                await self._move(joints, "slow")
        if self.direction == "right":
            turning_joint = turning_joint - (SO_101_JOINT_0_INCREMENT * multiplier)
            if turning_joint <= SO_101_JOINT_0_MIN_DEG:
                self.direction = "left"
            else:  
                joints[0] = turning_joint          
                await self._move(joints, "slow")

        
        
        
    


# verb -> method. One entry per capability.
STEPS = {
    "wave": Greeter.wave,
    "thumbsDown": Greeter.thumbs_down,
    "zero": Greeter.zero,
    "find": Greeter.find_person,
    "run": Greeter.run,
    "sway": Greeter.sway,
}

async def main(verb):
    robot = await connect()
    greeter = Greeter(robot)
    try:
        step = STEPS.get(verb)
        if step is None:
            print(f"unknown step '{verb}'. steps: {', '.join(STEPS)}")
            return
        await step(greeter)
    finally:
        await robot.close()


if __name__ == "__main__":
    verb = sys.argv[1] if len(sys.argv) > 1 else "run"
    asyncio.run(main(verb))