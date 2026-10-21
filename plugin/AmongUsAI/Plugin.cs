using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using AmongUs.GameOptions;
using BepInEx;
using BepInEx.Configuration;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using Il2CppInterop.Runtime;
using Il2CppInterop.Runtime.InteropTypes;
using Il2CppInterop.Runtime.InteropTypes.Arrays;
using InnerNet;
using UnityEngine;
using UObject = UnityEngine.Object;

namespace AmongUsAI;

[BepInProcess("Among Us.exe")]
[BepInPlugin("AmongUsAI", "AmongUsAI", "1.0.0-dev")]
public class Plugin : BasePlugin
{
	public enum MapType
	{
		Ship = 0,
		Hq = 1,
		Pb = 2,
		Fungle = 3,
		Airship = 4
	}

	[HarmonyPatch(typeof(ShipStatus), "OnEnable")]
	public static class ShipStatusUpdate
	{
		public static void Prefix(ShipStatus __instance)
		{
			map = (MapType)__instance.Type;
		}
	}

	[HarmonyPatch(typeof(PolusShipStatus), "OnEnable")]
	public static class PolusShipStatusUpdate
	{
		public static void Prefix(PolusShipStatus __instance)
		{
			map = MapType.Pb;
		}
	}

	[HarmonyPatch(typeof(AirshipStatus), "OnEnable")]
	public static class AirshipStatusUpdate
	{
		public static void Prefix(AirshipStatus __instance)
		{
			map = MapType.Airship;
		}
	}

	[HarmonyPatch(typeof(MeetingHud), "Awake")]
	public static class MeetingOpenUpdate
	{
		public static void Postfix(MeetingHud __instance)
		{
			inMeeting = true;
#pragma warning disable CS0618
			int discussionTime = GameOptionsManager.Instance.CurrentGameOptions.GetInt(Int32OptionNames.DiscussionTime);
			int votingTime = GameOptionsManager.Instance.CurrentGameOptions.GetInt(Int32OptionNames.VotingTime);
#pragma warning restore CS0618
			File.WriteAllText("timerData.txt", (discussionTime + votingTime) + "\n");
			var allPlayerControls = GetAllPlayerControls();
			for (int i = 0; i < allPlayerControls.Count; i++)
			{
				PlayerControl current = allPlayerControls[i];
				if ((UObject)(object)current == (UObject)null)
				{
					continue;
				}
				NetworkedPlayerInfo.PlayerOutfit currentOutfit = current.CurrentOutfit;
				if (currentOutfit == null)
				{
					continue;
				}
				currentOutfit.HatId = "hat_NoHat";
				currentOutfit.VisorId = "visor_EmptyVisor0";
			}
		}
	}

	[HarmonyPatch(typeof(MeetingHud), "Close")]
	public static class MeetingCloseUpdate
	{
		public static void Postfix(MeetingHud __instance)
		{
			inMeeting = false;
		}
	}

	[HarmonyPatch(typeof(InnerNetClient), "Update")]
	public static class ClientUpdate
	{
		public static void Postfix(InnerNetClient __instance)
		{
			int state = (int)__instance.GameState;
			if (state != 2 && state != 1)
			{
				inMeeting = false;
			}
			if (state == 3)
			{
				SetInGame(false);
			}
		}
	}

	[HarmonyPatch(typeof(ChatController), "AddChat")]
	public static class Chat_Pipe_Patch
	{
		public static void Prefix(ChatController __instance, PlayerControl sourcePlayer, string chatText)
		{
			if (sourcePlayer == null || sourcePlayer.Data == null || sourcePlayer.Data.IsDead)
			{
				return;
			}
			File.AppendAllText("chatData.txt", TranslateColorName(sourcePlayer.Data.ColorName) + ": " + chatText + "\n");
		}
	}

	// Which room a world position is in. Same approach already used for the
	// room line in the snapshot: test the point against every room's collider.
	private static string RoomNameAtPoint(Vector2 point)
	{
		try
		{
			var allRooms = ShipStatus.Instance.AllRooms;
			for (int i = 0; i < allRooms.Length; i++)
			{
				PlainShipRoom room = allRooms[i];
				if (room == null || room.roomArea == null)
				{
					continue;
				}
				if (room.roomArea.OverlapPoint(point))
				{
					return TranslateSystemTypes(room.RoomId);
				}
			}
		}
		catch
		{
		}
		return "";
	}

	[HarmonyPatch(typeof(PlayerControl), nameof(PlayerControl.MurderPlayer))]
	public static class Kill_Pipe_Patch
	{
		// Postfix, not Finalizer. Harmony Finalizers on IL2CPP targets are not
		// reliably invoked - the wrapper is generated and the finalizer hook is
		// dropped - so this patch produced an empty killData.txt for the whole
		// project, and there was no way to tell whether the bot had ever killed
		// anyone or the recorder was simply dead. A Postfix runs.
		public static void Postfix(PlayerControl __instance, PlayerControl target)
		{
			if (__instance == null || target == null || __instance.Data == null || target.Data == null)
			{
				return;
			}
			File.AppendAllText("killData.txt", TranslateColorName(__instance.Data.ColorName) + ", " + TranslateColorName(target.Data.ColorName) + "\n");
			// Also record WHERE and WHEN, so the harness can tell the model "that
			// happened, and you were three tiles away" instead of only learning
			// that someone is dead. A player hears a kill and knows roughly where
			// from; without this the bot had no idea a kill had happened at all.
			try
			{
				Vector2 vic = target.GetTruePosition();
				Vector2 kil = __instance.GetTruePosition();
				Vector2 me = PlayerControl.LocalPlayer != null
					? PlayerControl.LocalPlayer.GetTruePosition() : vic;
				string room = "";
				try
				{
					room = RoomNameAtPoint(vic);
				}
				catch
				{
				}
				File.WriteAllText("killWhere.txt",
					TranslateColorName(__instance.Data.ColorName) + " " +
					TranslateColorName(target.Data.ColorName) + " " +
					Math.Round(vic.x, 2) + " " + Math.Round(vic.y, 2) + " " +
					Math.Round(GetDistance(vic, me), 1) + " " + room + Environment.NewLine);
			}
			catch
			{
			}
			// Witnesses: everyone alive standing next to the victim when they died.
			// The Python side uses this to reason about who could have killed whom.
			try
			{
				Vector2 victimPos = target.GetTruePosition();
				string presence = "[";
				var all = GetAllPlayerControls();
				for (int i = 0; i < all.Count; i++)
				{
					PlayerControl witness = all[i];
					if (witness == null || witness == target || witness == __instance || witness.Data == null || witness.Data.IsDead)
					{
						continue;
					}
					float d = GetDistance(victimPos, witness.GetTruePosition());
					if (d <= 4.0f)
					{
						presence += TranslateColorName(witness.Data.ColorName) + "/" + Math.Round(d, 1) + ", ";
					}
				}
				if (presence.Length > 1)
				{
					presence = presence.Remove(presence.Length - 2);
				}
				presence += "]";
				File.WriteAllText("killPresence.txt", presence + "\n");
			}
			catch
			{
			}
		}
	}

	private static float GetDistance(Vector2 a, Vector2 b)
	{
		float dx = a.x - b.x;
		float dy = a.y - b.y;
		return (float)Math.Sqrt(dx * dx + dy * dy);
	}

	[HarmonyPatch(typeof(PlayerControl), "StartMeeting")]
	public static class Meeting_Pipe_Patch
	{
		public static void Finalizer(PlayerControl __instance, NetworkedPlayerInfo target)
		{
			if (__instance == null || __instance.Data == null)
			{
				return;
			}
			File.WriteAllText("meetingData.txt", TranslateColorName(__instance.Data.ColorName) + "\n");
			List<NetworkedPlayerInfo> allData = GetAllPlayerData();
			string text = "[";
			for (int i = 0; i < allData.Count; i++)
			{
				if (allData[i].IsDead)
				{
					text += TranslateColorName(allData[i].ColorName) + ", ";
				}
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]\n";
			text += "[";
			for (int i = 0; i < allData.Count; i++)
			{
				text += allData[i].PlayerName + "/" + TranslateColorName(allData[i].ColorName) + ", ";
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]\n";
			File.AppendAllText("meetingData.txt", text);
		}
	}

	[HarmonyPatch(typeof(PlayerControl), "OnGameStart")]
	public static class Game_Start_Patch
	{
		public static void Finalize(PlayerControl __instance)
		{
			SetInGame(true);
		}
	}

	[HarmonyPatch(typeof(PlayerControl), "OnGameEnd")]
	public static class Game_End_Patch
	{
		public static void Finalize(PlayerControl __instance)
		{
			SetInGame(false);
		}
	}

	[HarmonyPatch(typeof(PlayerControl), "FixedUpdate")]
	public static class Data_Pipe_Patch
	{
		private static int lastWriteTick;

		private static bool hasWritten;

		public static void Postfix(PlayerControl __instance)
		{
			if ((UObject)(object)__instance == (UObject)null)
			{
				return;
			}
			if ((UObject)(object)ShipStatus.Instance == (UObject)null || (UObject)(object)PlayerControl.LocalPlayer == (UObject)null)
			{
				SetInGame(false);
				return;
			}
			// Only the local player: this runs on PlayerControl.FixedUpdate, which fires for
			// every player object every physics frame.
			if (!((UObject)(object)__instance == (UObject)(object)PlayerControl.LocalPlayer))
			{
				return;
			}
			// These are not populated until the round actually starts.
			if (__instance.Data == null || __instance.myTasks == null || ShipStatus.Instance.AllRooms == null)
			{
				return;
			}
			SetInGame(true);

			// FixedUpdate runs ~50x/sec; writing the snapshot that often is pure I/O overhead
			// for the Python side, which polls far slower than this anyway.
			int now = Environment.TickCount;
			if (hasWritten && now - lastWriteTick < 50)
			{
				return;
			}
			lastWriteTick = now;
			hasWritten = true;

			bool isImpostor = isPlayerImposter(__instance.Data);
			bool hasFixLightsTask = false;
			string text = "";

			text += __instance.GetTruePosition().x + " " + __instance.GetTruePosition().y + "\n";
			text += isImpostor ? "impostor\n" : "crewmate\n";

			var tasks = __instance.myTasks.ToArray();
			int numTasks = tasks.Length;
			bool skipGhostTask = numTasks > 0 && __instance.Data.IsDead
				&& tasks[0].StartAt == SystemTypes.Hallway
				&& tasks[0].TaskType == TaskTypes.SubmitScan;

			text += "[";
			bool skipFirst = skipGhostTask;
			for (int i = 0; i < numTasks; i++)
			{
				if (skipFirst)
				{
					skipFirst = false;
					continue;
				}
				PlayerTask item = tasks[i];
				text += TranslateTaskTypes(item.TaskType);
				if (i != numTasks - 1)
				{
					text += ", ";
				}
				if (item.TaskType == TaskTypes.FixLights)
				{
					hasFixLightsTask = true;
				}
			}
			text += "]";
			text += "\n";

			text += "[";
			skipFirst = skipGhostTask;
			for (int i = 0; i < numTasks; i++)
			{
				if (skipFirst)
				{
					skipFirst = false;
					continue;
				}
				PlayerTask item = tasks[i];
				try
				{
					if (map.ToString() != "Ship")
					{
						text += TranslateSystemTypes(item.StartAt) + "(" + Math.Round(item.Locations[0].x) + "/" + Math.Round(item.Locations[0].y) + "), ";
						continue;
					}
					string location = TranslateSystemTypes(item.StartAt);
					if (item.TaskType == TaskTypes.VentCleaning && item.StartAt == SystemTypes.Reactor)
					{
						location = TranslateSystemTypes(item.StartAt) + "(" + Math.Round(item.Locations[0].x) + "/" + Math.Round(item.Locations[0].y) + ")";
					}
					text += location + ", ";
				}
				catch
				{
					text += TranslateSystemTypes(item.StartAt) + "(-0/-0), ";
				}
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]";
			text += "\n";

			if (!isImpostor)
			{
				text += "[";
				for (int i = 0; i < numTasks; i++)
				{
					try
					{
						PlayerTask item = tasks[i];
						NormalPlayerTask normalTask = ((Il2CppObjectBase)item).TryCast<NormalPlayerTask>();
						if (normalTask == null)
						{
							continue;
						}
						if (item.TaskType == TaskTypes.RebootWifi)
						{
							File.WriteAllText("wifiTaskData.txt", normalTask.TaskTimer.ToString());
						}
						text += normalTask.taskStep + "/" + normalTask.MaxStep;
						if (i != numTasks - 1)
						{
							text += ", ";
						}
					}
					catch
					{
					}
				}
				text += "]";
				text += "\n";
			}
			else
			{
				text += "[]";
				text += "\n";
			}

			text += map;
			text += "\n";
			text += __instance.Data.IsDead ? "1" : "0";
			text += "\n";
			text += inMeeting ? "1" : "0";
			text += "\n";
#pragma warning disable CS0618
			text += GameOptionsManager.Instance.CurrentGameOptions.GetFloat(FloatOptionNames.PlayerSpeedMod) + "\n";
#pragma warning restore CS0618
			text += __instance.CurrentOutfit.ColorId + "\n";

			Vector2 truePosition = __instance.GetTruePosition();
			string roomName = TranslateSystemTypes(SystemTypes.Outside);
			var allRooms = ShipStatus.Instance.AllRooms;
			for (int i = 0; i < allRooms.Length; i++)
			{
				PlainShipRoom room = allRooms[i];
				if (room == null || room.roomArea == null)
				{
					continue;
				}
				if (room.roomArea.OverlapPoint(truePosition))
				{
					roomName = TranslateSystemTypes(room.RoomId);
				}
			}
			text += roomName + "\n";
			text += hasFixLightsTask ? "1" : "0";
			text += "\n";

			var allPlayerControls = GetAllPlayerControls();

			text += "[";
			for (int i = 0; i < allPlayerControls.Count; i++)
			{
				PlayerControl item = allPlayerControls[i];
				if (item == null)
				{
					continue;
				}
				Vector2 otherPos = item.GetTruePosition();
				if (truePosition.x != otherPos.x && truePosition.y != otherPos.y)
				{
					text += TranslateColorName(item.Data.ColorName) + "/" + otherPos.x + "/" + otherPos.y + ", ";
				}
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]";
			text += "\n";

			text += "[";
			for (int i = 0; i < allPlayerControls.Count; i++)
			{
				PlayerControl item = allPlayerControls[i];
				if (item == null)
				{
					continue;
				}
				Vector2 otherPos = item.GetTruePosition();
				if (truePosition.x != otherPos.x && truePosition.y != otherPos.y)
				{
					text += TranslateColorName(item.Data.ColorName) + "/" + (item.inVent ? "1" : "0") + ", ";
				}
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]";
			text += "\n";

			text += "[";
			for (int i = 0; i < allPlayerControls.Count; i++)
			{
				PlayerControl item = allPlayerControls[i];
				if (item == null)
				{
					continue;
				}
				Vector2 otherPos = item.GetTruePosition();
				if (truePosition.x != otherPos.x && truePosition.y != otherPos.y)
				{
					text += TranslateColorName(item.Data.ColorName) + "/" + (item.Data.IsDead ? "1" : "0") + ", ";
				}
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]";
			text += "\n";

			WriteAtomic("sendData.txt", text);

			// Local role (RoleTypes: Engineer=3, Scientist=2, Tracker=10, etc).
			// Written separately so the 15-line sendData contract is untouched.
			try
			{
				WriteAtomic("roleData.txt", ((int)__instance.Data.RoleType) + "\n");
			}
			catch
			{
			}

			// Let the bot drive real game UI instead of clicking fixed pixels.
			PollCommands();
			WriteUiCoords();
		WriteAbilityData();
		WriteDetectiveData();
		WriteScientistData();
		WriteJudgeData();
		WriteVentData();
		WriteUiState();
			WriteMinigameState();
			WriteMinigameControls();

			WriteVentOptions();


			WriteSabotageButtons();



			WriteTaskRoutes(AllMyTasks());

			if (!isImpostor)
			{
				return;
			}

			string impText = "[";
			for (int i = 0; i < allPlayerControls.Count; i++)
			{
				PlayerControl item = allPlayerControls[i];
				if (item == null || !isPlayerImposter(item.Data))
				{
					continue;
				}
				Vector2 otherPos = item.GetTruePosition();
				if (truePosition.x != otherPos.x && truePosition.y != otherPos.y)
				{
					impText += TranslateColorName(item.Data.ColorName) + "/" + (item.Data.IsDead ? "1" : "0") + ", ";
				}
			}
			if (impText.Length > 1)
			{
				impText = impText.Remove(impText.Length - 2);
			}
			impText += "]";
			impText += "\n";
			impText += __instance.Data.IsDead ? "-1" : GetKillTimer() + "\n";
			File.WriteAllText("imposterData.txt", impText);
		}
	}

	private static readonly FieldInfo killTimerField =
		typeof(PlayerControl).GetField("killTimer", BindingFlags.NonPublic | BindingFlags.Instance);

	private static string GetKillTimer()
	{
		try
		{
			object value = killTimerField.GetValue(PlayerControl.LocalPlayer);
			return value == null ? "0" : Convert.ToString(value);
		}
		catch
		{
			return "0";
		}
	}

	public static string TranslateTaskTypes(TaskTypes type)
	{
		switch (type)
		{
			case TaskTypes.SubmitScan: return "Submit Scan";
			case TaskTypes.PrimeShields: return "Prime Shields";
			case TaskTypes.FuelEngines: return "Fuel Engines";
			case TaskTypes.ChartCourse: return "Chart Course";
			case TaskTypes.StartReactor: return "Start Reactor";
			case TaskTypes.SwipeCard: return "Swipe Card";
			case TaskTypes.ClearAsteroids: return "Clear Asteroids";
			case TaskTypes.UploadData: return "Upload Data";
			case TaskTypes.InspectSample: return "Inspect Sample";
			case TaskTypes.EmptyChute: return "Empty Chute";
			case TaskTypes.EmptyGarbage: return "Empty Garbage";
			case TaskTypes.AlignEngineOutput: return "Align Engine Output";
			case TaskTypes.FixWiring: return "Fix Wiring";
			case TaskTypes.CalibrateDistributor: return "Calibrate Distributor";
			case TaskTypes.DivertPower: return "Divert Power";
			case TaskTypes.UnlockManifolds: return "Unlock Manifolds";
			case TaskTypes.ResetReactor: return "Reset Reactor";
			case TaskTypes.FixLights: return "Fix Lights";
			case TaskTypes.CleanO2Filter: return "Clean O2 Filter";
			case TaskTypes.FixComms: return "Fix Communications";
			case TaskTypes.RestoreOxy: return "Restore Oxygen";
			case TaskTypes.StabilizeSteering: return "Stabilize Steering";
			case TaskTypes.AssembleArtifact: return "Assemble Artifact";
			case TaskTypes.SortSamples: return "Sort Samples";
			case TaskTypes.MeasureWeather: return "Measure Weather";
			case TaskTypes.EnterIdCode: return "Enter ID Code";
			case TaskTypes.BuyBeverage: return "Buy Beverage";
			case TaskTypes.ProcessData: return "Process Data";
			case TaskTypes.RunDiagnostics: return "Run Diagnostics";
			case TaskTypes.WaterPlants: return "Water Plants";
			case TaskTypes.MonitorOxygen: return "Monitor Oxygen";
			case TaskTypes.StoreArtifacts: return "Store Artifacts";
			case TaskTypes.FillCanisters: return "Fill Canisters";
			case TaskTypes.FixWeatherNode: return "Activate Weather Nodes";
			case TaskTypes.InsertKeys: return "Insert Keys";
			case TaskTypes.ResetSeismic: return "Reset Seismic Stabilizers";
			case TaskTypes.ScanBoardingPass: return "Scan Boarding Pass";
			case TaskTypes.OpenWaterways: return "Open Waterways";
			case TaskTypes.ReplaceWaterJug: return "Replace Water Jug";
			case TaskTypes.RepairDrill: return "Repair Drill";
			case TaskTypes.AlignTelescope: return "Align Telescope";
			case TaskTypes.RecordTemperature: return "Record Temperature";
			case TaskTypes.RebootWifi: return "Reboot Wifi";
			case TaskTypes.PolishRuby: return "Polish Ruby";
			case TaskTypes.ResetBreakers: return "Reset Breakers";
			case TaskTypes.Decontaminate: return "Decontaminate";
			case TaskTypes.MakeBurger: return "Make Burger";
			case TaskTypes.UnlockSafe: return "Unlock Safe";
			case TaskTypes.SortRecords: return "Sort Records";
			case TaskTypes.PutAwayPistols: return "Put Away Pistols";
			case TaskTypes.FixShower: return "Fix Shower";
			case TaskTypes.CleanToilet: return "Clean Toilet";
			case TaskTypes.DressMannequin: return "Dress Mannequin";
			case TaskTypes.PickUpTowels: return "Pick Up Towels";
			case TaskTypes.RewindTapes: return "Rewind Tapes";
			case TaskTypes.StartFans: return "Start Fans";
			case TaskTypes.DevelopPhotos: return "Develop Photos";
			case TaskTypes.GetBiggolSword: return "Get Biggol Sword";
			case TaskTypes.PutAwayRifles: return "Put Away Rifles";
			case TaskTypes.StopCharles: return "Stop Charles";
			case TaskTypes.VentCleaning: return "Vent Cleaning";
			case TaskTypes.None: return "None";
			case TaskTypes.BuildSandcastle: return "Build Sandcastle";
			case TaskTypes.CatchFish: return "Catch Fish";
			case TaskTypes.CollectShells: return "Collect Shells";
			case TaskTypes.LiftWeights: return "Lift Weights";
			case TaskTypes.RoastMarshmallow: return "Roast Marshmallow";
			case TaskTypes.TestFrisbee: return "Test Frisbee";
			case TaskTypes.CollectSamples: return "Collect Samples";
			case TaskTypes.CollectVegetables: return "Collect Vegetables";
			case TaskTypes.HoistSupplies: return "Hoist Supplies";
			case TaskTypes.MineOres: return "Mine Ores";
			case TaskTypes.PolishGem: return "Polish Gem";
			case TaskTypes.ReplaceParts: return "Replace Parts";
			case TaskTypes.HelpCritter: return "Help Critter";
			case TaskTypes.CrankGenerator: return "Crank Generator";
			case TaskTypes.FixAntenna: return "Fix Antenna";
			case TaskTypes.TuneRadio: return "Tune Radio";
			case TaskTypes.MushroomMixupSabotage: return "Mushroom Mixup Sabotage";
			case TaskTypes.ExtractFuel: return "Extract Fuel";
			case TaskTypes.MonitorMushroom: return "Monitor Mushroom";
			case TaskTypes.PlayVideogame: return "Play Videogame";
			default: return type.ToString();
		}
	}

	public static string TranslateSystemTypes(SystemTypes type)
	{
		switch (type)
		{
			case SystemTypes.Hallway: return "Hallway";
			case SystemTypes.Storage: return "Storage";
			case SystemTypes.Cafeteria: return "Cafeteria";
			case SystemTypes.Reactor: return "Reactor";
			case SystemTypes.UpperEngine: return "Upper Engine";
			case SystemTypes.Nav: return "Navigation";
			case SystemTypes.Admin: return "Admin";
			case SystemTypes.Electrical: return "Electrical";
			case SystemTypes.LifeSupp: return "Oxygen";
			case SystemTypes.Shields: return "Shields";
			case SystemTypes.MedBay: return "MedBay";
			case SystemTypes.Security: return "Security";
			case SystemTypes.Weapons: return "Weapons";
			case SystemTypes.LowerEngine: return "Lower Engine";
			case SystemTypes.Comms: return "Communications";
			case SystemTypes.ShipTasks: return "Ship Tasks";
			case SystemTypes.Doors: return "Doors";
			case SystemTypes.Sabotage: return "Sabotage";
			case SystemTypes.Decontamination: return "Decontamination";
			case SystemTypes.Launchpad: return "Launchpad";
			case SystemTypes.LockerRoom: return "Locker Room";
			case SystemTypes.Laboratory: return "Laboratory";
			case SystemTypes.Balcony: return "Balcony";
			case SystemTypes.Office: return "Office";
			case SystemTypes.Greenhouse: return "Greenhouse";
			case SystemTypes.Dropship: return "Dropship";
			case SystemTypes.Decontamination2: return "Decontamination";
			case SystemTypes.Outside: return "Outside";
			case SystemTypes.Specimens: return "Specimen Room";
			case SystemTypes.BoilerRoom: return "Boiler Room";
			case SystemTypes.VaultRoom: return "Vault Room";
			case SystemTypes.Cockpit: return "Cockpit";
			case SystemTypes.Armory: return "Armory";
			case SystemTypes.Kitchen: return "Kitchen";
			case SystemTypes.ViewingDeck: return "Viewing Deck";
			case SystemTypes.HallOfPortraits: return "Hall Of Portraits";
			case SystemTypes.CargoBay: return "Cargo Bay";
			case SystemTypes.Ventilation: return "Ventilation";
			case SystemTypes.Showers: return "Showers";
			case SystemTypes.Engine: return "Engine Room";
			case SystemTypes.Brig: return "The Brig";
			case SystemTypes.MeetingRoom: return "Meeting Room";
			case SystemTypes.Records: return "Records Room";
			case SystemTypes.Lounge: return "Lounge Room";
			case SystemTypes.GapRoom: return "Gap Room";
			case SystemTypes.MainHall: return "Main Hall";
			case SystemTypes.Medical: return "Medical";
			case SystemTypes.Decontamination3: return "Decontamination";
			case SystemTypes.Zipline: return "Zipline";
			case SystemTypes.MiningPit: return "Mining Pit";
			case SystemTypes.FishingDock: return "Fishing Dock";
			case SystemTypes.RecRoom: return "Rec Room";
			case SystemTypes.Lookout: return "Lookout";
			case SystemTypes.Beach: return "Beach";
			case SystemTypes.Highlands: return "Highlands";
			case SystemTypes.Jungle: return "Jungle";
			case SystemTypes.SleepingQuarters: return "Sleeping Quarters";
			case SystemTypes.MushroomMixupSabotage: return "Mushroom Mixup Sabotage";
			case SystemTypes.HeliSabotage: return "Heli Sabotage";
			default: return type.ToString();
		}
	}

	public static bool isPlayerImposter(NetworkedPlayerInfo playerInfo)
	{
		if (playerInfo == null || playerInfo.Role == null)
		{
			return false;
		}
		return playerInfo.Role.TeamType == RoleTeamTypes.Impostor;
	}

	// ---------------------------------------------------------------------
	// Role abilities.
	//
	// RoleBehaviour.UseAbility() is the game's own generic ability trigger and
	// every role overrides it (EngineerRole.UseAbility enters a vent, etc), so
	// this needs no per-role special casing. Target-based roles
	// (GuardianAngel/Shapeshifter) also expose direct Cmd* entry points.
	// ---------------------------------------------------------------------
	private static RoleBehaviour LocalRole()
	{
		PlayerControl lp = PlayerControl.LocalPlayer;
		if (lp == null || lp.Data == null)
		{
			return null;
		}
		return lp.Data.Role;
	}

	public static bool UsePrimaryAbility()
	{
		try
		{
			RoleBehaviour role = LocalRole();
			if (role == null)
			{
				return false;
			}
			// No ability button on screen means the role has no primary ability, or
			// it is dead, or it is on cooldown. Saying "ok" here is how a Phantom
			// ends up pretending it vented.
			HudManager hud = HudManager.Instance;
			if (hud != null && hud.AbilityButton != null &&
				!hud.AbilityButton.gameObject.activeInHierarchy)
			{
				return false;
			}
			if (role.IsDead)
			{
				return false;
			}
			role.UseAbility();
			return true;
		}
		catch
		{
			return false;
		}
	}

	public static bool UseSecondaryAbility()
	{
		try
		{
			RoleBehaviour role = LocalRole();
			if (role == null)
			{
				return false;
			}
			// Only Detective and Phantom have a second ability; for every other role
			// this button is inactive, so refuse rather than pretend.
			HudManager hud = HudManager.Instance;
			if (hud != null)
			{
				if (hud.SecondaryAbilityButton == null ||
					!hud.SecondaryAbilityButton.gameObject.activeInHierarchy)
				{
					return false;
				}
			}
			if (role.IsDead)
			{
				return false;
			}
			role.UseSecondaryAbility();
			return true;
		}
		catch
		{
			return false;
		}
	}

	// Lets the bot verify input without guessing: when the Admin table is used,
	// MapBehaviour.IsOpen flips, so we can prove which controller button is USE.
	private static void WriteUiState()
	{
		try
		{
			string text = "";
			try
			{
				bool adminOpen = MapBehaviour.Instance != null && MapBehaviour.Instance.IsOpen;
				text += "adminopen " + (adminOpen ? 1 : 0) + "\n";
			}
			catch
			{
				text += "adminopen 0\n";
			}
			try
			{
				PlayerControl lp = PlayerControl.LocalPlayer;
				text += "taskpanel " + (lp != null && lp.myTasks != null ? lp.myTasks.Count : -1) + "\n";
			}
			catch
			{
				text += "taskpanel -1\n";
			}
			WriteAtomic("uiState.txt", text);
		}
		catch
		{
		}
	}

	// The impostor opens the sabotage map with its own button (HudManager
	// .SabotageButton) from anywhere on the map - there is no need to walk to
	// Admin. That button opens the same map, whose entries are SabotageButton
	// objects; we enumerate them so the bot can click any of them (including
	// every door hijack) without hardcoded coordinates.
	public static bool OpenSabotageMap()
	{
		try
		{
			HudManager hud = HudManager.Instance;
			if (hud == null || hud.SabotageButton == null)
			{
				return false;
			}
			hud.SabotageButton.DoClick();
			return true;
		}
		catch
		{
			return false;
		}
	}

	// Resolve a sabotage name to the SystemTypes room it belongs to.
	// The map's own MapRoom objects carry a public `room` field, so every entry
	// identifies itself - no calibration, no pixels, nothing to retune when the
	// resolution changes.
	private static bool NameToSystem(string name, out SystemTypes type, out bool isDoor)
	{
		type = SystemTypes.Hallway;
		isDoor = true;
		if (string.IsNullOrEmpty(name))
		{
			return false;
		}
		string n = name.Trim().ToLowerInvariant().Replace(" ", "").Replace("_", "");

		if (n == "reactor" || n == "reactorSabotage")
		{
			type = SystemTypes.Reactor;
			isDoor = false;
			return true;
		}
		if (n == "oxygen" || n == "o2" || n == "lifesupp")
		{
			type = SystemTypes.LifeSupp;
			isDoor = false;
			return true;
		}
		if (n == "comms" || n == "communications" || n == "communication")
		{
			type = SystemTypes.Comms;
			isDoor = false;
			return true;
		}
		if (n == "lights" || n == "shields")
		{
			type = SystemTypes.Shields;
			isDoor = false;
			return true;
		}
		if (n == "heli" || n == "helisabotage")
		{
			type = SystemTypes.HeliSabotage;
			isDoor = false;
			return true;
		}
		if (n == "mushroom" || n == "mixup" || n == "mushroommixupsabotage")
		{
			type = SystemTypes.MushroomMixupSabotage;
			isDoor = false;
			return true;
		}

		// door rooms - the sabotagable ones
		if (n == "cafeteria" || n == "caf")
		{
			type = SystemTypes.Cafeteria;
		}
		else if (n == "upper" || n == "upperengine" || n == "uppereng" || n == "reactorupper")
		{
			type = SystemTypes.UpperEngine;
		}
		else if (n == "medbay" || n == "medica" || n == "medical")
		{
			type = SystemTypes.MedBay;
		}
		else if (n == "security" || n == "sec" || n == "secroom")
		{
			type = SystemTypes.Security;
		}
		else if (n == "electrical" || n == "elec")
		{
			type = SystemTypes.Electrical;
		}
		else if (n == "lower" || n == "lowerengine" || n == "lowereng")
		{
			type = SystemTypes.LowerEngine;
		}
		else if (n == "storage" || n == "stor")
		{
			type = SystemTypes.Storage;
		}
		else
		{
			// try the enum name directly
			try
			{
				type = (SystemTypes)Enum.Parse(typeof(SystemTypes), name, true);
				isDoor = type != SystemTypes.Reactor && type != SystemTypes.LifeSupp &&
						 type != SystemTypes.Comms && type != SystemTypes.Shields &&
						 type != SystemTypes.HeliSabotage && type != SystemTypes.MushroomMixupSabotage;
				return true;
			}
			catch
			{
				return false;
			}
		}
		return true;
	}

	// Unity's FindObjectsOfType only returns ACTIVE objects, and the sabotage map,
	// the vent-travel buttons and the vitals panels are all inactive whenever
	// their UI is closed. Enumerating with the default overload therefore found
	// zero of them even in a live game, so the includeInactive overload is used
	// wherever we inspect UI that lives behind a closed panel.
	private static T[] FindAll<T>() where T : UnityEngine.Object
	{
		try
		{
			return UnityEngine.Object.FindObjectsOfType<T>(true);
		}
		catch
		{
			try
			{
				return UnityEngine.Object.FindObjectsOfType<T>();
			}
			catch
			{
				return null;
			}
		}
	}

	// Enumerate the sabotage map. MapBehaviour owns a MapRoom per entry and each
	// one reports its own SystemTypes, so the Python side gets real names.
	private static void WriteSabotageButtons()
	{
		try
		{
			List<string> rows = new List<string>();
			var all = FindAll<MapRoom>();
			int found = all != null ? all.Length : 0;
			int doors = 0;
			if (all != null)
			{
				for (int i = 0; i < all.Length; i++)
				{
					MapRoom r = all[i];
					if (r == null)
					{
						continue;
					}
					SystemTypes st = r.room;
					if (st == SystemTypes.Hallway || st == SystemTypes.Sabotage)
					{
						continue;
					}
					rows.Add(st + " " + (int)st + " " + r.gameObject.activeInHierarchy);
				}
			}
			// canonical door order, matching the SystemTypes values
			rows.Sort(delegate (string a, string b)
			{
				string[] pa = a.Split(' ');
				string[] pb = b.Split(' ');
				return int.Parse(pa[1]).CompareTo(int.Parse(pb[1]));
			});
			for (int i = 0; i < rows.Count; i++)
			{
				string[] p = rows[i].Split(' ');
				if (p[0] == "Reactor" || p[0] == "LifeSupp" || p[0] == "Comms" ||
					p[0] == "Shields" || p[0] == "HeliSabotage" || p[0] == "MushroomMixupSabotage")
				{
					continue;
				}
				doors++;
			}
			string text = "#found=" + found + " entries=" + rows.Count + " doors=" + doors + Environment.NewLine;
			for (int i = 0; i < rows.Count; i++)
			{
				text += i + " " + rows[i] + Environment.NewLine;
			}
			File.WriteAllText("sabotageButtons.txt", text);
		}
		catch
		{
		}
	}

	// Trigger a sabotage by name. This drives the game's own MapRoom object, so it
	// behaves exactly like pressing the entry on the map and is completely
	// independent of screen size.
	public static bool ClickSabotage(string name)
	{
		try
		{
			SystemTypes target;
			bool isDoor;
			if (!NameToSystem(name, out target, out isDoor))
			{
				return false;
			}
			var all = FindAll<MapRoom>();
			if (all == null)
			{
				return false;
			}
			for (int i = 0; i < all.Length; i++)
			{
				MapRoom r = all[i];
				if (r == null || r.room != target)
				{
					continue;
				}
				if (isDoor)
				{
					r.SabotageDoors();
				}
				else if (target == SystemTypes.Reactor)
				{
					r.SabotageReactor();
				}
				else if (target == SystemTypes.LifeSupp)
				{
					r.SabotageOxygen();
				}
				else if (target == SystemTypes.Comms)
				{
					r.SabotageComms();
				}
				else if (target == SystemTypes.Shields)
				{
					r.SabotageLights();
				}
				else if (target == SystemTypes.HeliSabotage)
				{
					r.SabotageHeli();
				}
				else if (target == SystemTypes.MushroomMixupSabotage)
				{
					r.SabotageMushroomMixup();
				}
				else
				{
					return false;
				}
				return true;
			}
			return false;
		}
		catch
		{
			return false;
		}
	}

	// Vents are IUsable in the game, but Il2CppInterop does not emit IUsable as a
	// a private `currentTarget` Vent. Enumerating them and calling DoClick() on
	// the right one avoids pixel-clicking the vent menu entirely.
	private static FieldInfo ventButtonTargetField;

	private static FieldInfo GetVentButtonTargetField()
	{
		if (ventButtonTargetField == null)
		{
			ventButtonTargetField = typeof(VentButton).GetField("currentTarget",
				BindingFlags.NonPublic | BindingFlags.Instance);
		}
		return ventButtonTargetField;
	}

	private static List<VentButton> FindVentButtons()
	{
		List<VentButton> found = new List<VentButton>();
		try
		{
			var all = FindAll<VentButton>();
			if (all == null)
			{
				return found;
			}
			for (int i = 0; i < all.Length; i++)
			{
				if (all[i] != null)
				{
					found.Add(all[i]);
				}
			}
		}
		catch
		{
		}
		return found;
	}

	private static void WriteVentOptions()
	{
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || !lp.inVent)
			{
				File.WriteAllText("ventOptions.txt", "");
				return;
			}
			Camera cam = Camera.main;
			if (cam == null)
			{
				return;
			}
			float h = Screen.height;
			FieldInfo f = GetVentButtonTargetField();
			string text = "";
			if (f != null)
			{
				foreach (VentButton b in FindVentButtons())
				{
					try
					{
						Vent target = f.GetValue(b) as Vent;
						if (target == null)
						{
							continue;
						}
						Vector3 p = cam.WorldToScreenPoint(b.transform.position);
						text += target.Id + " " + (int)p.x + " " + (int)(h - p.y) + "\n";
					}
					catch
					{
					}
				}
			}
			File.WriteAllText("ventOptions.txt",
				text + "#field=" + (f != null) + " found=" + FindVentButtons().Count + Environment.NewLine);
		}
		catch
		{
		}
	}

	public static bool VentTravelTo(int ventId)
	{
		try
		{
			FieldInfo f = GetVentButtonTargetField();
			if (f == null)
			{
				return false;
			}
			List<VentButton> buttons = FindVentButtons();
			foreach (VentButton b in buttons)
			{
				try
				{
					Vent target = f.GetValue(b) as Vent;
					if (target != null && target.Id == ventId)
					{
						b.DoClick();
						return true;
					}
				}
				catch
				{
				}
			}
			return false;
		}
		catch
		{
			return false;
		}
	}

	// Vents are IUsable in the game, but Il2CppInterop does not emit IUsable as a
	// managed interface, so RoleBehaviour.SetUsableTarget(IUsable) is not callable
	// from C#. Instead we publish vent positions *and* the vent graph, and the bot
	// walks to a legal vent and presses USE, letting the game run its own vent
	// interaction. Vent.Left/Right/Center encode the real connectivity, so the bot
	// never tries to jump from MedBay to Admin like it used to.
	// Publishes whether a task panel is currently open, and which one.
	//
	// The harness had been inferring this by looking for wire ends and sample
	// tubes in screenshots, and every screenshot heuristic was wrong in a
	// different way: it missed an open panel, matched a closed one, and could
	// not tell a wiring panel from a lights panel. The game already knows, exactly:
	// Minigame.Instance is non-null while a panel is up, Minigame.TaskType says
	// which, and amOpening/amClosing say where in the transition it is.
	//
	// This is the authoritative answer, so the bot stops guessing.
	private static void WriteMinigameState()
	{
		try
		{
			Minigame mg = Minigame.Instance;
			if (mg == null)
			{
				File.WriteAllText("minigameState.txt", "open 0\ntask \nopening 0\nclosing 0\n");
				return;
			}
			Il2CppObjectBase obj = (Il2CppObjectBase)(object)mg;
			// amOpening/amClosing are protected, so they are not reachable as
			// properties from here. TaskType is public and is what matters.
			TaskTypes tt = mg.TaskType;
			File.WriteAllText("minigameState.txt",
				"open 1\n" +
				"task " + tt.ToString() + "\n" +
				"opening 0\n" +
				"closing 0\n" +
				"#numeric " + (int)tt + Environment.NewLine);
		}
		catch (Exception e)
		{
			try
			{
				File.WriteAllText("minigameState.txt", "open 0\ntask \n#error " + e.Message + Environment.NewLine);
			}
			catch
			{
			}
		}
	}

	// Publishes the on-screen positions of whatever the open minigame wants
	// clicked or dragged.
	//
	// The plugin runs INSIDE the game, so it can read the real transform of every
	// interactive element and convert it to screen coordinates. That replaces
	// template matching and hardcoded pixel offsets entirely for these tasks,
	// which is the only approach that can be trusted: the pixel approach has been
	// wrong for every task it was applied to, and wrong differently each time.
	//
	//   SimonSaysGame (Start Reactor) - Buttons[] is a public SpriteRenderer
	//     array, as are LeftLights[]. So the exact click target for each of the
	//     four pads is known, and so is where to sample the screen colour to see
	//     which one is lit. No template matching, no guessing where the pads are.
	//
	//   EmptyGarbageMinigame (Empty Trash) - Handle is a public Collider2D, so
	//     the lever's position is known, and `finished` is readable by reflection
	//     so the bot can tell the drag actually completed rather than assuming it.
	private static void WriteMinigameControls()
	{
		try
		{
			Minigame mg = Minigame.Instance;
			if (mg == null)
			{
				File.WriteAllText("minigameControls.txt", "none\n");
				return;
			}
			Camera cam = Camera.main;
			if (cam == null)
			{
				File.WriteAllText("minigameControls.txt", "nocam\n");
				return;
			}
			float h = Screen.height;
			StringBuilder sb = new StringBuilder();
			Il2CppObjectBase obj = (Il2CppObjectBase)(object)mg;
			sb.Append("task " + mg.TaskType.ToString() + "\n");
			// The GameObject's own name. This is plain Unity API, so it always
			// works, and for a prefab instance it names the panel. The previous
			// attempt used the managed proxy's type, which is the BASE class -
			// the file said 'class Minigame' - because `mg` is statically typed as
			// Minigame and GetType() returns that, not the runtime subclass. So no
			// fields were found, and the harness wrongly believed the geometry
			// build was loaded.
			string goName = "";
			try
			{
				goName = mg.gameObject.name;
				sb.Append("gobject " + goName + "\n");
			}
			catch
			{
			}
			// Resolve the CONCRETE minigame class by GameObject name, so its real
			// fields can be read.
			System.Type concrete = ResolveMinigameType(goName);
			try
			{
				sb.Append("class " + (concrete != null ? concrete.Name : "unresolved")
					+ "\n");
			}
			catch
			{
			}
			// Generic geometry: every public SpriteRenderer, Collider2D and
			// Transform on the open panel, with its screen position. Deliberately
			// not task-specific: Calibrate Distributor's panel has no Slider field
			// and no class named after it, so anything hand-written for it was a
			// guess. Enumerating what the panel actually exposes is not.
			WriteGenericFields(sb, obj, concrete, cam, h);
			// Everything the concrete class holds, private fields included. The
			// targeted readers below stay for the two panels that need more than
			// raw state, but nothing depends on them any more.
			WriteMinigameFields(sb, obj, concrete, cam, h);

			SimonSaysGame sg = obj.TryCast<SimonSaysGame>();
			if (sg != null)
			{
				sb.Append("type simon\n");
				WriteSpritePositions(sb, sg.Buttons, "button", cam, h);
				WriteSpritePositions(sb, sg.LeftLights, "light", cam, h);
				// The lights' own SpriteRenderer colour is published too, so the
				// bot does not have to sample the screen to work out which pad is
				// lit. The old solver guessed a 3x3 pixel grid and looked for one
				// hardcoded RGB value; the game already knows the colour of every
				// light at every instant, exactly.
				WriteSpriteColours(sb, sg.LeftLights, "lightcol");
				WriteSpriteColours(sb, sg.Buttons, "buttoncol");
				// roundDownIndex/roundUpIndex say which way the pads are laid out,
				// so the bot can map a lit light to the pad that shares its angle.
				try
				{
					sb.Append("roundDown " + sg.roundDownIndex + "\n");
					sb.Append("roundUp " + sg.roundUpIndex + "\n");
				}
				catch
				{
				}
				// `operations` is the queue the game itself works through, and it
				// is private. Publishing it is what tells the bot how many pads it
				// has to press and when they have all been played - there is no
				// other signal for "the sequence has finished", which is why
				// reading the light colours alone could never tell one step from
				// a whole round: between two flashes every light is dark.
				//
				// The op codes are FlashOp 256, AnimateOp 128, ReAnimateOp 32 and
				// FailOp 64, so a value below 4 is a pad index the player must
				// press. That is the sequence, in order.
				try
				{
					FieldInfo of = typeof(SimonSaysGame).GetField("operations",
						BindingFlags.NonPublic | BindingFlags.Instance);
					if (of != null)
					{
						object q = of.GetValue(sg);
						if (q != null)
						{
							System.Collections.IEnumerable en = q as System.Collections.IEnumerable;
							if (en != null)
							{
								int count = 0;
								foreach (object item in en)
								{
									try
									{
										int v = Convert.ToInt32(item);
										// The op codes are FlashOp 256,
										// AnimateOp 128, ReAnimateOp 32 and
										// FailOp 64, and a flash of button n
										// is queued as n | 256. The old
										// filter here was "v < 4", on the
										// belief that a small number was a
										// button index - so it matched
										// NOTHING, and the sequence lines
										// this was supposed to publish were
										// never printed. The values are
										// published raw now, and the
										// sequence itself is read from the
										// task's Data bytes, which is where
										// the game actually keeps it.
										sb.Append("op " + count + " " + v + "\n");
									}
									catch
									{
									}
									count++;
								}
							}
						}
					}
				}
				catch
				{
				}
				File.WriteAllText("minigameControls.txt", sb.ToString());
				return;
			}

			EmptyGarbageMinigame eg = obj.TryCast<EmptyGarbageMinigame>();
			if (eg != null)
			{
				sb.Append("type garbage\n");
				try
				{
					Vector3 p = cam.WorldToScreenPoint(eg.Handle.transform.position);
					sb.Append("handle " + (int)p.x + " " + (int)(h - p.y) + "\n");
				}
				catch
				{
				}
				// `finished` and `leverInput` are private. Read them rather than
				// having the bot assume a drag worked.
				try
				{
					FieldInfo ff = typeof(EmptyGarbageMinigame).GetField("finished",
						BindingFlags.NonPublic | BindingFlags.Instance);
					bool fin = ff != null && (bool)ff.GetValue(eg);
					sb.Append("finished " + (fin ? "1" : "0") + "\n");
				}
				catch
				{
				}
				try
				{
					FieldInfo lf = typeof(EmptyGarbageMinigame).GetField("leverInput",
						BindingFlags.NonPublic | BindingFlags.Instance);
					if (lf != null)
					{
						sb.Append("lever " + Convert.ToSingle(lf.GetValue(eg)).ToString("0.00") + "\n");
					}
				}
				catch
				{
				}
				// HandleRange is the lever's full travel, so the bot knows how far
				// to drag it instead of guessing a fraction of the screen.
				try
				{
					FloatRange hr = eg.HandleRange;
					sb.Append("handlelow " + Convert.ToSingle(hr.min).ToString("0.00") + "\n");
					sb.Append("handlehigh " + Convert.ToSingle(hr.max).ToString("0.00") + "\n");
				}
				catch
				{
				}
				// On the second stage the panel is in Storage and there is nothing
				// to drag - the trash just falls. Say so, so the solver waits
				// instead of dragging at a lever that is not there.
				try
				{
					sb.Append("hasHandle " + (eg.Handle != null ? "1" : "0") + "\n");
				}
				catch
				{
				}
				File.WriteAllText("minigameControls.txt", sb.ToString());
				return;
			}

			sb.Append("type other\n");
			File.WriteAllText("minigameControls.txt", sb.ToString());
		}
		catch (Exception e)
		{
			try
			{
				File.WriteAllText("minigameControls.txt", "error " + e.Message + Environment.NewLine);
			}
			catch
			{
			}
		}
	}

	// Per-name cache. A single static was wrong in two ways at once: the scan
	// accepted the first Minigame subclass it tried (TryCast's wrapper is not
	// null on failure, so it "succeeded" on TaskAdderGame while the panel was
	// something else entirely), and caching that one answer meant every later
	// panel got the same wrong class.
	private static System.Collections.Generic.Dictionary<string, System.Type> minigameTypeCache = new System.Collections.Generic.Dictionary<string, System.Type>();

	// Find the concrete class of the open minigame BY NAME.
	//
	// The GameObject's name is the reliable identifier here - it has been correct
	// in every live run, reporting things like "SampleMinigame(Clone)" - and the
	// class is then found by matching that name against the loaded proxy types.
	// No TryCast is involved, so there is no way to accept a wrong type.
	private static System.Type ResolveMinigameType(string gameObjectName)
	{
		if (string.IsNullOrEmpty(gameObjectName))
		{
			return null;
		}
		string want = gameObjectName;
		int clone = want.IndexOf("(Clone)");
		if (clone > 0)
		{
			want = want.Substring(0, clone);
		}
		System.Type cached;
		if (minigameTypeCache.TryGetValue(want, out cached))
		{
			return cached;
		}
		try
		{
			System.Reflection.Assembly[] asms = AppDomain.CurrentDomain.GetAssemblies();
			for (int a = 0; a < asms.Length; a++)
			{
				System.Type[] types;
				try
				{
					types = asms[a].GetTypes();
				}
				catch
				{
					continue;
				}
				for (int i = 0; i < types.Length; i++)
				{
					System.Type t = types[i];
					if (t == null || t.Name != want || t.IsAbstract)
					{
						continue;
					}
					if (!typeof(Minigame).IsAssignableFrom(t))
					{
						continue;
					}
					minigameTypeCache[want] = t;
					return t;
				}
			}
		}
		catch
		{
		}
		// Remember the miss too, so a panel whose class is not a loaded proxy
		// does not trigger a full assembly scan on every single tick.
		minigameTypeCache[want] = null;
		return null;
	}

	private static void WriteGenericFields(StringBuilder sb, Il2CppObjectBase obj, System.Type concrete, Camera cam, float h)
	{
		if (concrete == null)
		{
			return;
		}
		try
		{
			System.Type t = concrete;
			Il2CppObjectBase typed = TypedWrapper(obj, concrete);
			FieldInfo[] fields = t.GetFields(BindingFlags.Public | BindingFlags.Instance);
			for (int i = 0; i < fields.Length; i++)
			{
				System.Type ft = fields[i].FieldType;
				string name = fields[i].Name;
				try
				{
					if (ft == typeof(SpriteRenderer[]))
					{
						SpriteRenderer[] arr = fields[i].GetValue(typed) as SpriteRenderer[];
						if (arr == null)
						{
							continue;
						}
						for (int j = 0; j < arr.Length; j++)
						{
							if (arr[j] == null)
							{
								continue;
							}
							Vector3 p = cam.WorldToScreenPoint(arr[j].transform.position);
							sb.Append("sprite " + name + " " + j + " " + (int)p.x + " " + (int)(h - p.y) + "\n");
						}
					}
					else if (ft == typeof(SpriteRenderer))
					{
						SpriteRenderer sr = fields[i].GetValue(typed) as SpriteRenderer;
						if (sr == null)
						{
							continue;
						}
						Vector3 p = cam.WorldToScreenPoint(sr.transform.position);
						sb.Append("sprite " + name + " -1 " + (int)p.x + " " + (int)(h - p.y) + "\n");
					}
					else if (ft == typeof(Collider2D))
					{
						Collider2D col = fields[i].GetValue(typed) as Collider2D;
						if (col == null)
						{
							continue;
						}
						Vector3 p = cam.WorldToScreenPoint(col.transform.position);
						sb.Append("collider " + name + " -1 " + (int)p.x + " " + (int)(h - p.y) + "\n");
					}
					else if (ft == typeof(Transform))
					{
						Transform tr = fields[i].GetValue(typed) as Transform;
						if (tr == null)
						{
							continue;
						}
						Vector3 p = cam.WorldToScreenPoint(tr.position);
						sb.Append("transform " + name + " -1 " + (int)p.x + " " + (int)(h - p.y) + "\n");
					}
				}
				catch
				{
				}
			}
		}
		catch
		{
		}
	}

	// ---------------------------------------------------------------------
	// Generic minigame state, read off whichever panel is actually open.
	//
	// WriteGenericFields above only knows about four field TYPES, and the
	// targeted readers further up only know about two panel CLASSES. Both are
	// the same mistake: the panel that is open is whatever the player opened,
	// so a reader written for one panel publishes nothing - or, worse, plausible
	// nothing - for every other one. Calibrate Distributor's panel is a
	// SweepMinigame whose interesting state is a HorizontalGauge[] and a private
	// spinnerIdx, and neither is a SpriteRenderer, so it published nothing at
	// all and the bot fell back to guessing pixel coordinates.
	//
	// So the state is read GENERICALLY: every instance field and every readable
	// property on the concrete class, private ones included, walked up the
	// hierarchy. What each field MEANS is the game's business, not this file's.
	// A panel patched in a later build, or a class nobody has seen before, is
	// published in full without anyone editing this file.
	//
	// Three kinds of line, so the Python side can tell what it is looking at:
	//
	//   f <name> <value>                 a scalar member
	//   r <name> <x> <y>                 a Unity object, at its screen position
	//   c <name> <r> <g> <b>            ...and its own SpriteRenderer colour
	//   f <name>[<i>]/<member> <value>  an element, recursed into
	//
	// A null Unity object is printed rather than skipped: "the lever is not
	// there" is exactly the fact a solver needs to decide not to drag it.
	//
	// MEMBERS ARE READ AS PROPERTIES, NOT FIELDS. Il2CppInterop generates a
	// C# property for every il2cpp field, public ones for private il2cpp fields
	// included, and generates almost no real C# fields. An earlier version of
	// this walked GetFields() and therefore published nothing at all for any
	// panel - it emitted one line, and the bot concluded the panel had no state.
	// ---------------------------------------------------------------------
	private static readonly Dictionary<System.Type, PropertyInfo[]> reflectedProps =
		new Dictionary<System.Type, PropertyInfo[]>();

	// Reflection over IL2CPP proxies allocates wrappers, and this runs on every
	// tick, so the member lists are looked up once per type.
	private static PropertyInfo[] PropsOf(System.Type t)
	{
		PropertyInfo[] cached;
		if (reflectedProps.TryGetValue(t, out cached))
		{
			return cached;
		}
		try
		{
			PropertyInfo[] all = t.GetProperties(BindingFlags.Public | BindingFlags.NonPublic |
				BindingFlags.Instance | BindingFlags.DeclaredOnly);
			List<PropertyInfo> keep = new List<PropertyInfo>();
			for (int i = 0; i < all.Length; i++)
			{
				// An indexed property (SimonSaysGame.Item) needs an argument and
				// is not state, so it is skipped rather than called blindly.
				MethodInfo getter = all[i].GetGetMethod(true);
				if (all[i].CanRead && getter != null &&
					getter.GetParameters().Length == 0 &&
					all[i].GetIndexParameters().Length == 0)
				{
					keep.Add(all[i]);
				}
			}
			cached = keep.ToArray();
		}
		catch
		{
			cached = new PropertyInfo[0];
		}
		reflectedProps[t] = cached;
		return cached;
	}

	// A scalar, formatted, or null when the value is NOT a scalar and the
	// caller has to handle it as an object.
	private static string Scalar(object value)
	{
		if (value == null)
		{
			return null;
		}
		try
		{
			if (value is bool)
			{
				return ((bool)value) ? "1" : "0";
			}
			if (value is int || value is uint || value is short || value is ushort ||
				value is byte || value is sbyte || value is long)
			{
				return Convert.ToString(value, System.Globalization.CultureInfo.InvariantCulture);
			}
			if (value is float)
			{
				return ((float)value).ToString("0.####", System.Globalization.CultureInfo.InvariantCulture);
			}
			if (value is double)
			{
				return ((double)value).ToString("0.####", System.Globalization.CultureInfo.InvariantCulture);
			}
			if (value is string)
			{
				string sv = (string)value;
				return sv.Replace("\n", " ").Replace("\r", " ");
			}
			if (value is System.Enum)
			{
				// Both the number and the name: the number is stable across
				// patches, the name is what a human reads.
				return Convert.ToInt64(value).ToString(System.Globalization.CultureInfo.InvariantCulture) +
					"/" + value.ToString();
			}
		}
		catch
		{
		}
		return null;
	}

	// Screen position of a Unity object, in client pixels with a top-left
	// origin - the same convention as every other position in this file, so it
	// is directly usable as a pyautogui coordinate once the window origin is
	// added.
	private static string ScreenPos(object value, Camera cam, float h)
	{
		try
		{
			if (cam == null)
			{
				return null;
			}
			Component c = value as Component;
			if (c == null)
			{
				return null;
			}
			Vector3 p = cam.WorldToScreenPoint(c.transform.position);
			return (int)p.x + " " + (int)(h - p.y);
		}
		catch
		{
			return null;
		}
	}

	// Reads a count off an il2cpp array, list or queue. Those types are neither
	// System.Array nor System.Collections.IEnumerable, so Length, Count and the
	// indexer are found by name rather than by a cast. The name check is what
	// stops a MonoBehaviour that happens to have a Count from being read as a
	// collection.
	private static bool LooksLikeCollection(System.Type t)
	{
		string n = t.Name;
		return n.IndexOf("Array", StringComparison.Ordinal) >= 0 ||
			n.IndexOf("Queue", StringComparison.Ordinal) >= 0 ||
			n.IndexOf("List", StringComparison.Ordinal) >= 0 ||
			n.IndexOf("Collection", StringComparison.Ordinal) >= 0 ||
			n.IndexOf("Stack", StringComparison.Ordinal) >= 0;
	}

	private static bool TryCount(object coll, System.Type t, out int n)
	{
		n = 0;
		if (coll == null || !LooksLikeCollection(t))
		{
			return false;
		}
		try
		{
			System.Array sa = coll as System.Array;
			if (sa != null)
			{
				n = sa.Length;
				return true;
			}
			PropertyInfo p = t.GetProperty("Length", BindingFlags.Public | BindingFlags.Instance) ??
				t.GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
			if (p != null)
			{
				n = Convert.ToInt32(p.GetValue(coll, null));
				return true;
			}
			FieldInfo f = t.GetField("Count", BindingFlags.Public | BindingFlags.Instance);
			if (f != null)
			{
				n = Convert.ToInt32(f.GetValue(coll));
				return true;
			}
		}
		catch
		{
		}
		return false;
	}

	private static object TryIndex(object coll, System.Type t, int i)
	{
		try
		{
			PropertyInfo p = t.GetProperty("Item", BindingFlags.Public | BindingFlags.Instance);
			if (p != null && p.GetIndexParameters().Length == 1)
			{
				return p.GetValue(coll, new object[] { i });
			}
			MethodInfo m = t.GetMethod("get_Item", BindingFlags.Public | BindingFlags.Instance);
			if (m != null)
			{
				return m.Invoke(coll, new object[] { i });
			}
		}
		catch
		{
		}
		return null;
	}

	// A value worth recursing into: a primitive, an enum, or a small struct
	// such as Vector2, Color or FloatRange. Everything else is a Unity object
	// with a whole world behind it - recursing into a Sprite means hundreds of
	// lines of triangle indices, and the file is re-read every tick. The check
	// is on the DECLARED type, so it costs nothing to make.
	private static bool IsLeafType(System.Type t)
	{
		return t != null && (t.IsPrimitive || t.IsEnum || t.IsValueType);
	}

	// Writes one line per fact about `value`, recursing into the scalars of
	// nested objects. A HorizontalGauge inside a SweepMinigame reports its own
	// Value and MaxValue; a Sprite behind it reports nothing, which is correct -
	// nobody solving a task needs a sprite's triangle list.
	private static int dumpLines;

	private static void WriteValue(StringBuilder sb, string label, object value,
		Camera cam, float h, int depth, bool withPos)
	{
		if (dumpLines > 400)
		{
			return;
		}
		if (value == null)
		{
			dumpLines++;
			sb.Append(label + " null\n");
			return;
		}
		try
		{
			string s = Scalar(value);
			if (s != null)
			{
				dumpLines++;
				sb.Append(label + " " + s + "\n");
				return;
			}
			if (withPos)
			{
				string p = ScreenPos(value, cam, h);
				if (p != null)
				{
					dumpLines++;
					sb.Append(label + " " + p + "\n");
					// A sprite's own colour is the game's answer to "is this lit
					// right now", which is exactly what a solver would otherwise
					// go and sample a pixel to find out.
					try
					{
						SpriteRenderer sr = value as SpriteRenderer;
						if (sr != null)
						{
							Color c = sr.color;
							dumpLines++;
							sb.Append("c " + label.Substring(2) + " " +
								(int)(c.r * 255f) + " " + (int)(c.g * 255f) + " " +
								(int)(c.b * 255f) + "\n");
						}
					}
					catch
					{
					}
					return;
				}
			}
			System.Type vt = value.GetType();
			int count;
			if (TryCount(value, vt, out count))
			{
				// Queue<int> is the sequence SimonSaysGame works through, and the
				// only way to know how many steps there are and when they have
				// all been played. Enumerated rather than assumed, because the
				// alternative is a timeout.
				for (int i = 0; i < count; i++)
				{
					// withPos stays on for elements: a panel's buttons, tubes and
					// lights ARE arrays of sprites, and their positions and
					// colours are the state a solver needs.
					WriteValue(sb, label + "[" + i + "]", TryIndex(value, vt, i),
						cam, h, depth, true);
				}
				dumpLines++;
				sb.Append(label + ".count " + count + "\n");
				return;
			}
			if (depth <= 0)
			{
				return;
			}
			PropertyInfo[] ps = PropsOf(vt);
			for (int i = 0; i < ps.Length; i++)
			{
				if (!IsLeafType(ps[i].PropertyType))
				{
					continue;
				}
				object pv;
				try
				{
					pv = ps[i].GetValue(value, null);
				}
				catch
				{
					continue;
				}
				WriteValue(sb, label + "/" + ps[i].Name, pv, cam, h, depth - 1, false);
			}
		}
		catch
		{
		}
	}

	// A wrapper of the panel's OWN type, over the same native object.
	//
	// Minigame.Instance is statically typed as Minigame, so it hands back a
	// Minigame wrapper even when the open panel is a SweepMinigame. The native
	// pointer is correct, but every generated getter on the concrete class
	// refuses it: PropertyInfo.GetValue throws TargetException "Object does not
	// match target type" for all fourteen members, and the panel therefore looks
	// to the bot like a panel with no state whatsoever. The same mismatch broke
	// MinigameCall and the sprite reader for every panel that was not literally
	// a Minigame.
	//
	// Il2CppInterop's wrapper constructor takes the native pointer, so the right
	// wrapper is one call away.
	private static Il2CppObjectBase TypedWrapper(Il2CppObjectBase obj, System.Type concrete)
	{
		if (obj == null || concrete == null)
		{
			return obj;
		}
		try
		{
			if (concrete.IsInstanceOfType(obj))
			{
				return obj;
			}
			IntPtr ptr = IL2CPP.Il2CppObjectBaseToPtrNotNull(obj);
			if (ptr == IntPtr.Zero)
			{
				return obj;
			}
			ConstructorInfo ctor = concrete.GetConstructor(
				BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
				null, new System.Type[] { typeof(IntPtr) }, null);
			if (ctor == null)
			{
				return obj;
			}
			Il2CppObjectBase typed = ctor.Invoke(new object[] { ptr }) as Il2CppObjectBase;
			return typed ?? obj;
		}
		catch
		{
			return obj;
		}
	}

	private static void WriteMinigameFields(StringBuilder sb, Il2CppObjectBase obj,
		System.Type concrete, Camera cam, float h)
	{
		if (concrete == null || obj == null)
		{
			return;
		}
		Il2CppObjectBase typed = TypedWrapper(obj, concrete);
		dumpLines = 0;
		try
		{
			System.Type t = concrete;
			int levels = 0;
			// Stop at UnityEngine.Object: everything above it is shared
			// boilerplate that says nothing about this panel.
			while (t != null && t != typeof(UnityEngine.Object) && levels < 10)
			{
				PropertyInfo[] ps = PropsOf(t);
				for (int i = 0; i < ps.Length; i++)
				{
					object pv;
					try
					{
						pv = ps[i].GetValue(typed, null);
					}
					catch
					{
						continue;
					}
					WriteValue(sb, "f " + ps[i].Name, pv, cam, h, 2, true);
				}
				t = t.BaseType;
				levels++;
			}
		}
		catch
		{
		}
	}

	// Call a public method on the open minigame with integer arguments.
	//
	// Every minigame that has a pressable control exposes it as a plain public
	// method - SweepMinigame.HitButton(int), SimonSaysGame.HitButton(int),
	// SampleMinigame.SelectTube(int) - and those are the exact methods the
	// panel's own buttons call. So this is not a shortcut around the UI: it IS
	// the UI, minus the part where a pixel has to land on the right sprite.
	// The refusal list is the panel's own lifecycle, which must never be
	// triggered from here: closing or beginning a minigame out of band leaves
	// the task in a state the game does not expect.
	public static string MinigameCall(string method, int[] args)
	{
		try
		{
			Minigame mg = Minigame.Instance;
			if (mg == null)
			{
				return "fail no minigame is open";
			}
			if (method == "Close" || method == "Begin" || method == "Open" ||
				method == "Instantiate" || method.StartsWith("Set", StringComparison.Ordinal) ||
				method.StartsWith("Co", StringComparison.Ordinal))
			{
				return "fail " + method + " is a lifecycle method and is not callable";
			}
			Il2CppObjectBase obj = (Il2CppObjectBase)(object)mg;
			string goName = "";
			try
			{
				goName = mg.gameObject.name;
			}
			catch
			{
			}
			System.Type concrete = ResolveMinigameType(goName);
			if (concrete == null)
			{
				return "fail could not resolve the class behind " + goName;
			}
			MethodInfo mi = concrete.GetMethod(method,
				BindingFlags.Public | BindingFlags.Instance);
			if (mi == null)
			{
				return "fail " + concrete.Name + " has no public " + method;
			}
			ParameterInfo[] ps = mi.GetParameters();
			if (ps.Length > args.Length)
			{
				return "fail " + method + " needs " + ps.Length + " argument(s)";
			}
			object[] argv = new object[ps.Length];
			for (int i = 0; i < ps.Length; i++)
			{
				System.Type pt = ps[i].ParameterType;
				if (pt == typeof(int))
				{
					argv[i] = args[i];
				}
				else if (pt == typeof(bool))
				{
					argv[i] = args[i] != 0;
				}
				else if (pt == typeof(float))
				{
					argv[i] = (float)args[i];
				}
				else
				{
					return "fail " + method + " argument " + (i + 1) + " is a " + pt.Name;
				}
			}
			mi.Invoke(TypedWrapper(obj, concrete), argv);
			return "ok " + concrete.Name + "." + method;
		}
		catch (Exception e)
		{
			// The inner exception is the real one: reflection wraps whatever
			// the target threw, and the wrapper's own type says nothing about
			// what went wrong. The message is included because "IOException"
			// on its own does not say WHICH file.
			Exception inner = e.InnerException ?? e;
			return "fail exception " + inner.GetType().Name + ": " + inner.Message;
		}
	}

	// The TASK's own state, not the panel's.
	//
	// The minigame class does not hold the answer - the TASK does. Start Reactor
	// keeps its button sequence in NormalPlayerTask.Data, a byte[], and Inspect
	// Sample keeps the id of the anomalous tube in the same array, so walking
	// the panel's class hierarchy never finds either. The task is a different
	// object, and it is the one that knows what the right answer is.
	//
	//   taskdata <n> <v>   byte n of NormalPlayerTask.Data
	//   taskstep <n>      NormalPlayerTask.taskStep
	//   taskmaxstep <n>   NormalPlayerTask.MaxStep
	//
	// What the bytes MEAN differs by task, and the game does not label them:
	//
	//   Start Reactor  Data[0] is the LENGTH of the sequence and Data[1..] are
	//                  the button indices, in order. taskStep is how many of
	//                  them have been pressed this round, and it is reset to 0
	//                  at the start of every round.
	//
	//   Inspect Sample Data[0] is a STATE CODE, not a count: 64 means a tube
	//                  may be selected, and Data[1] is then the anomalous
	//                  tube. 32 means the processing has finished, 128 means
	//                  the lower buttons are up.
	//
	// Both are published raw. The solver knows which task it is on, and
	// guessing at the meaning here would be exactly the kind of assumption
	// that has cost this project a round before.
	private static void WriteTaskState(StringBuilder sb, Minigame mg)
	{
		try
		{
			NormalPlayerTask nt = mg.MyNormTask;
			if (nt == null)
			{
				return;
			}
			Il2CppStructArray<byte> data = nt.Data;
			if (data != null)
			{
				for (int i = 0; i < data.Length; i++)
				{
					sb.Append("taskdata " + i + " " + data[i] + "\n");
				}
			}
			sb.Append("taskstep " + nt.taskStep + "\n");
			sb.Append("taskmaxstep " + nt.MaxStep + "\n");
		}
		catch
		{
		}
	}

	// Read one member off the open panel by name, whatever its visibility.
	//
	// The members that matter are private il2cpp fields - timer, spinnerIdx -
	// and Il2CppInterop exposes those as public properties, but a name is
	// safer than a compile-time reference: a field that moves or disappears
	// then costs one lookup rather than the whole plugin.
	private static object ReadMember(object owner, System.Type type, string name)
	{
		try
		{
			PropertyInfo[] all = PropsOf(type);
			for (int i = 0; i < all.Length; i++)
			{
				if (all[i].Name == name)
				{
					return all[i].GetValue(owner, null);
				}
			}
		}
		catch
		{
		}
		return null;
	}

	// The HOT state of the open panel: the few numbers a solver needs while it
	// is racing the game, published on EVERY FixedUpdate.
	//
	// This is a separate file, written at full rate, because the snapshot
	// pipeline is throttled to 50ms and that is not fast enough. Calibrate
	// Distributor's dial is only inside its target zone for a fraction of a
	// revolution, and a solver that samples the window at 20Hz can miss it
	// entirely.
	//
	// Every number here is read out of the game, and the arithmetic is the
	// game's own, done in float so the numbers are the ones the game itself
	// would compute:
	//
	//   Calibrate Distributor (SweepMinigame)
	//     the dial's angle is (int)(SpinRate * timer) degrees, and the target
	//     is zero, so the distance to it is min(rem, 360 - rem). The game
	//     accepts a press when that distance is under 13 degrees.
	//
	//   Start Reactor (SimonSaysGame)
	//     the sequence is the task's Data bytes: Data[0] is how long it is,
	//     Data[1..] are the button indices.
	//
	//   Inspect Sample (SampleMinigame)
	//     Data[0] is the panel's state - 64 means a tube may be picked - and
	//     Data[1] is then the anomalous tube.
	//
	// The task's own bytes are published for every task, because which of
	// these meanings applies depends on the task and the game does not say.
	// The SpriteRenderer[] held by a named member of the open panel, read the
	// same way the generic dump reads everything else - by name, through the
	// reflection path that is already known to work on these proxies.
	private static SpriteRenderer[] SpritesOf(Il2CppObjectBase owner,
		System.Type type, string name)
	{
		try
		{
			PropertyInfo[] all = PropsOf(type);
			for (int i = 0; i < all.Length; i++)
			{
				if (all[i].Name != name)
				{
					continue;
				}
				object v = all[i].GetValue(owner, null);
				if (v == null)
				{
					return null;
				}
				System.Type vt = v.GetType();
				int count;
				if (!TryCount(v, vt, out count))
				{
					return null;
				}
				List<SpriteRenderer> outList = new List<SpriteRenderer>();
				for (int j = 0; j < count; j++)
				{
					outList.Add(TryIndex(v, vt, j) as SpriteRenderer);
				}
				return outList.ToArray();
			}
		}
		catch
		{
		}
		return null;
	}

	private static void WriteMinigameHot(StringBuilder sb, Minigame mg)
	{
		try
		{
			if (mg == null)
			{
				return;
			}
			sb.Append("task " + mg.TaskType + "\n");

			NormalPlayerTask nt = mg.MyNormTask;
			if (nt != null)
			{
				Il2CppStructArray<byte> data = nt.Data;
				if (data != null)
				{
					for (int i = 0; i < data.Length; i++)
					{
						sb.Append("data " + i + " " + data[i] + "\n");
					}
				}
				sb.Append("step " + nt.taskStep + "\n");
				sb.Append("maxstep " + nt.MaxStep + "\n");
			}

			string goName = "";
			try
			{
				goName = mg.gameObject.name;
			}
			catch
			{
			}
			System.Type concrete = ResolveMinigameType(goName);
			sb.Append("hotclass " + (concrete == null ? "null" : concrete.Name) + "\n");
			if (concrete == null)
			{
				return;
			}
			Il2CppObjectBase typed = TypedWrapper(mg, concrete);

			if (concrete.Name == "SimonSaysGame")
			{
				// Is the round's animation over?
				//
				// SimonSaysGame plays the sequence back before it will accept
				// a press, and a press issued DURING that playback is accepted
				// by the game and then silently thrown away when the playback
				// resets the press counter - which leaves the bot out of step
				// and makes its next press the wrong one.
				//
				// The game's own end-of-animation signal is its colour: the
				// playback turns every pad GREY as it starts and WHITE as it
				// ends, and nothing else makes a pad white while a playback is
				// running. The press echo is a brief blue flash on one pad, so
				// "at least one pad is white" is true whenever the player is
				// being allowed to press.
				try
				{
					SpriteRenderer[] pads = SpritesOf(typed, concrete, "Buttons");
					int anyWhite = 0;
					if (pads != null)
					{
						for (int i = 0; i < pads.Length; i++)
						{
							if (pads[i] == null)
							{
								continue;
							}
							Color c = pads[i].color;
							if (c.r > 0.95f && c.g > 0.95f && c.b > 0.95f)
							{
								anyWhite = 1;
								break;
							}
						}
					}
					sb.Append("pads " + (pads == null ? -1 : pads.Length) + "\n");
					sb.Append("roundready " + anyWhite + "\n");
				}
				catch (Exception e)
				{
					sb.Append("paderr " + e.GetType().Name + "\n");
				}
			}

			if (concrete.Name == "SweepMinigame")
			{
				object spin = ReadMember(typed, concrete, "SpinRate");
				object tim = ReadMember(typed, concrete, "timer");
				object idx = ReadMember(typed, concrete, "spinnerIdx");
				if (spin is float rate && tim is float timer)
				{
					// Exactly the game's own arithmetic: CalcXPerc() computes
					// (int)(SpinRate * timer) % 360 and takes the smaller of
					// that and 360 minus it.
					int whole = (int)(rate * timer);
					int rem = whole % 360;
					if (rem < 0)
					{
						rem += 360;
					}
					int dist = rem < 360 - rem ? rem : 360 - rem;
					sb.Append("spinrate " + rate.ToString("0.###",
						System.Globalization.CultureInfo.InvariantCulture) + "\n");
					sb.Append("angle " + rem + "\n");
					sb.Append("dist " + dist + "\n");
				}
				if (idx is int which)
				{
					sb.Append("spinner " + which + "\n");
				}
			}
		}
		catch
		{
		}
	}

	// Writes the hot file every FixedUpdate, with no throttle.
	//
	// This is a separate patch from the snapshot one on purpose: the snapshot
	// is throttled to 50ms because it is fifteen lines of text written for the
	// whole bot, and this is a dozen lines written for the solver that is
	// currently racing a moving dial.
	[HarmonyPatch(typeof(PlayerControl), "FixedUpdate")]
	public static class MinigameHotPatch
	{
		public static void Postfix(PlayerControl __instance)
		{
			try
			{
				if ((UObject)(object)__instance == (UObject)null)
				{
					return;
				}
				if (!((UObject)(object)__instance == (UObject)PlayerControl.LocalPlayer))
				{
					return;
				}
				StringBuilder sb = new StringBuilder();
				WriteMinigameHot(sb, Minigame.Instance);
				WriteAtomic("minigameHot.txt", sb.ToString());
			}
			catch
			{
			}
		}
	}

	private static void WriteSpriteColours(StringBuilder sb, SpriteRenderer[] sprites, string label)
	{
		if (sprites == null)
		{
			return;
		}
		try
		{
			int n = sprites.Length;
			for (int i = 0; i < n; i++)
			{
				if (sprites[i] == null)
				{
					continue;
				}
				Color c = sprites[i].color;
				sb.Append(label + " " + i + " " + (int)(c.r * 255f) + " " + (int)(c.g * 255f) + " " + (int)(c.b * 255f) + "\n");
			}
		}
		catch
		{
		}
	}

	private static void WriteSpritePositions(StringBuilder sb, SpriteRenderer[] sprites, string label, Camera cam, float h)
	{
		if (sprites == null)
		{
			return;
		}
		try
		{
			int n = sprites.Length;
			for (int i = 0; i < n; i++)
			{
				if (sprites[i] == null)
				{
					continue;
				}
				Vector3 p = cam.WorldToScreenPoint(sprites[i].transform.position);
				sb.Append(label + " " + i + " " + (int)p.x + " " + (int)(h - p.y) + "\n");
			}
		}
		catch
		{
		}
	}

	private static void WriteVentData()
	{		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || ShipStatus.Instance == null || ShipStatus.Instance.AllVents == null)
			{
				return;
			}
			Il2CppArrayBase<Vent> all = ShipStatus.Instance.AllVents;
			var byId = new Dictionary<int, Vent>();
			for (int i = 0; i < all.Length; i++)
			{
				if (all[i] != null)
				{
					byId[all[i].Id] = all[i];
				}
			}

			string text = "[";
			for (int i = 0; i < all.Length; i++)
			{
				Vent v = all[i];
				if (v == null)
				{
					continue;
				}
				Vector3 wp = v.transform.position;
				int left = v.Left != null ? v.Left.Id : -1;
				int right = v.Right != null ? v.Right.Id : -1;
				int center = v.Center != null ? v.Center.Id : -1;
				text += v.Id + "/" + wp.x + "/" + wp.y + "/" + left + "," + right + "," + center + ", ";
			}
			if (text.Length > 1)
			{
				text = text.Remove(text.Length - 2);
			}
			text += "]";
			WriteAtomic("ventData.txt", text + "\n");
		}
		catch
		{
		}
	}

	private static PlayerControl FindByColor(int colorIndex)
	{
		var all = GetAllPlayerControls();
		for (int i = 0; i < all.Count; i++)
		{
			if (all[i] != null && all[i].Data != null && TranslateColorName(all[i].Data.ColorName) == colorIndex)
			{
				return all[i];
			}
		}
		return null;
	}

	// Guardian Angel
	public static bool ProtectColor(int colorIndex)
	{
		try
		{
			PlayerControl target = FindByColor(colorIndex);
			if (target == null || PlayerControl.LocalPlayer == null)
			{
				return false;
			}
			PlayerControl.LocalPlayer.CmdCheckProtect(target);
			return true;
		}
		catch
		{
			return false;
		}
	}

	// Shapeshifter
	public static bool MimicColor(int colorIndex)
	{
		try
		{
			PlayerControl target = FindByColor(colorIndex);
			if (target == null || PlayerControl.LocalPlayer == null)
			{
				return false;
			}
			PlayerControl.LocalPlayer.CmdCheckShapeshift(target, true);
			return true;
		}
		catch
		{
			return false;
		}
	}

	// Role/ability state the Python side needs in order to decide what to do.
	private static void WriteAbilityData()
	{
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || lp.Data == null)
			{
				return;
			}
			RoleBehaviour role = lp.Data.Role;
			string text = "";
			text += "role " + ((int)lp.Data.RoleType) + "\n";
			if (role != null)
			{
				text += "isimpostor " + (role.IsImpostor ? 1 : 0) + "\n";
				text += "canvent " + (role.CanVent ? 1 : 0) + "\n";
				text += "cankill " + (role.CanUseKillButton ? 1 : 0) + "\n";
				text += "isdead " + (role.IsDead ? 1 : 0) + "\n";
			}
		text += "invent " + (lp.inVent ? 1 : 0) + "\n";
		text += "shapeshifted " + lp.ShapeshiftedPlayerID() + "\n";
		text += "protected " + (lp.protectedByGuardianThisRound ? 1 : 0) + "\n";

		// How many ability buttons the HUD is actually showing right now. Only
		// Detective and Phantom have a second ability in this build; reading the
		// live buttons means the model is never told the wrong count even if the
		// game adds or removes one.
		int count = 0;
		try
		{
			HudManager hud = HudManager.Instance;
			if (hud != null)
			{
				if (IsButtonUsable(hud.AbilityButton))
				{
					count++;
				}
				if (IsButtonUsable(hud.SecondaryAbilityButton))
				{
					count++;
				}
			}
		}
		catch
		{
		}
		text += "abilitycount " + count + "\n";
		WriteAtomic("abilityData.txt", text);
	}
	catch
	{
	}
}

	// Is this ability button actually on screen for the local player?
	private static bool IsButtonUsable(ActionButton b)
	{
		if (b == null)
		{
			return false;
		}
		try
		{
			return b.gameObject != null && b.gameObject.activeInHierarchy;
		}
		catch
		{
			return false;
		}
	}

	// Detective notes. DetectiveRole.notesPageInfos is the game's own record of
	// what the detective learned: one page per inspected body, carrying the
	// victim, the room the body was in, who was standing near it, and the
	// "impostor type" the game itself filled in. Reading that is the whole point
	// of the role, so it is published verbatim rather than guessed at.
	private static void WriteDetectiveData()
	{
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || lp.Data == null)
			{
				return;
			}
			DetectiveRole det = lp.Data.Role as DetectiveRole;
			if (det == null || det.notesPageInfos == null)
			{
				return;
			}
			StringBuilder sb = new StringBuilder();
			sb.Append("#pages ").Append(det.notesPageInfos.Count).Append(Environment.NewLine);
			for (int i = 0; i < det.notesPageInfos.Count; i++)
			{
				DetectiveNotesPageInfo page = det.notesPageInfos[i];
				if (page == null)
				{
					continue;
				}
				// one field per line: names and room names contain spaces, so a
				// single-line key=value encoding cannot be parsed unambiguously
				sb.Append("page ").Append(i).Append(Environment.NewLine);
				sb.Append("victim ").Append(page.victimPlayer != null
					? page.victimPlayer.name + " (" + ColorName(page.victimPlayer.Color) + ")"
					: "unknown").Append(Environment.NewLine);
				sb.Append("location ").Append(page.locationSet && page.locationName != null
					? page.locationName : "unknown").Append(Environment.NewLine);
				sb.Append("preposition ").Append(page.prepositionSet
					? page.prepositionStringName.ToString() : "none").Append(Environment.NewLine);
				sb.Append("impostor ").Append(page.impostorSet && page.impostorString != null
					? page.impostorString : "unknown").Append(Environment.NewLine);

				// The suspect list is "was this player standing near the body, and
				// were they alive at the time" - exactly what a detective reports.
				if (page.suspects != null)
				{
					for (int s = 0; s < page.suspects.Count; s++)
					{
						DetectiveSuspect sus = page.suspects[s];
						if (sus.playerInfo == null)
						{
							continue;
						}
						sb.Append("suspect ").Append(sus.playerInfo.name)
						  .Append(" (").Append(ColorName(sus.playerInfo.Color)).Append(")")
						  .Append(" wasDead ").Append(det.PlayerWasDead(sus) ? 1 : 0)
						  .Append(Environment.NewLine);
					}
				}
			}
			WriteAtomic("detectiveData.txt", sb.ToString());
		}
		catch
		{
		}
	}

	private static string ColorName(Color c)
	{
		try
		{
			int i = Convert.ToInt32(c);
			if (i < 0 || i >= Palette.ColorNames.Length)
			{
				return "?";
			}
			return Palette.ColorNames[i].ToString();
		}
		catch
		{
			return "?";
		}
	}

	// Scientist vitals. Each VitalsPanel is one player and already knows whether
	// they are dead or disconnected, so the sensor read is data, not pixels.
	private static void WriteScientistData()
	{
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || lp.Data == null)
			{
				return;
			}
			if (!(lp.Data.Role is ScientistRole))
			{
				return;
			}
			var panels = FindAll<VitalsPanel>();
			if (panels == null)
			{
				return;
			}
			StringBuilder sb = new StringBuilder();
			sb.Append("#panels ").Append(panels.Length).Append(Environment.NewLine);
			for (int i = 0; i < panels.Length; i++)
			{
				VitalsPanel p = panels[i];
				if (p == null || p.PlayerInfo == null)
				{
					continue;
				}
				string state = p.IsDead ? "DEAD" : (p.IsDiscon ? "DISCONNECTED" : "ALIVE");
				sb.Append(p.PlayerInfo.name)
				  .Append(" (").Append(ColorName(p.PlayerInfo.Color)).Append(") ")
				  .Append(state).Append(Environment.NewLine);
			}
			WriteAtomic("scientistData.txt", sb.ToString());
		}
		catch
		{
		}
	}

	// Judge: whether an overrule is available, and who it would target.
	private static void WriteJudgeData()
	{
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || lp.Data == null)
			{
				return;
			}
			JudgeRole jr = lp.Data.Role as JudgeRole;
			if (jr == null)
			{
				return;
			}
			StringBuilder sb = new StringBuilder();
			sb.Append("hasuse ").Append(jr.HasAnOverruleUse ? 1 : 0).Append(Environment.NewLine);
			sb.Append("used ").Append(jr.HasAlreadyOverruledThisMeeting ? 1 : 0).Append(Environment.NewLine);
			sb.Append("blocked ").Append(jr.IsBlockedByTasks() ? 1 : 0).Append(Environment.NewLine);
			WriteAtomic("judgeData.txt", sb.ToString());
		}
		catch
		{
		}
	}

	// Judge overrule: cast the extra vote against a player id.
	public static bool JudgeOverrule(int playerId)
	{
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || lp.Data == null)
			{
				return false;
			}
			JudgeRole jr = lp.Data.Role as JudgeRole;
			if (jr == null || !jr.HasAnOverruleUse || jr.HasAlreadyOverruledThisMeeting)
			{
				return false;
			}
			return jr.TryOverrule((PlayerId)playerId);
		}
		catch
		{
			return false;
		}
	}

	// File.WriteAllText truncates before writing, so the Python side can read the
	// file mid-write and get an empty or partial snapshot. Write a temp file and
	// swap it in with MoveFileEx(REPLACE_EXISTING), which is atomic. An earlier
	// Delete-then-Move left a window where the file simply did not exist, and
	// the bot's getGameData() crashed on it.
	private static void WriteAtomic(string path, string content)
	{
		try
		{
			string tmp = path + ".tmp";
			File.WriteAllText(tmp, content);
			File.Move(tmp, path, true);
		}
		catch
		{
		}
	}

	public static MapType map;

	public static bool inMeeting;

	// ---------------------------------------------------------------------
	// Control channel for the Python bot.
	//
	// The bot used to blind-click fixed pixel ratios for every UI control,
	// which broke on any resolution other than 1920x1080 (and was already
	// wrong on the current build). Instead the Python side drops a command in
	// botCmd.txt and the plugin drives the real game API. UI element positions
	// are read back out of the game's own layout in uiCoords.txt.
	// ---------------------------------------------------------------------
	public static bool SetChatOpen(bool open)
	{
		try
		{
			// InGamePlayerList is the mobile-style side panel and is NOT the chat
			// used in meetings, which is why opening it did nothing during a
			// meeting. HudManager.Chat (a ChatController) is the real one in both
			// contexts, and Toggle()/Close() are its own entry points.
			HudManager hud = HudManager.Instance;
			if (hud == null || hud.Chat == null)
			{
				return false;
			}
			if (open)
			{
				if (hud.Chat.IsClosedOrClosing)
				{
					hud.Chat.Toggle();
					return true;
				}
				// already open: the requested end state still holds
				return !hud.Chat.IsOpenOrOpening ? false : true;
			}
			if (hud.Chat.IsOpenOrOpening)
			{
				hud.Chat.Close();
				return true;
			}
			return true;
		}
		catch
		{
			return false;
		}
	}

	public static void PollCommands()
	{
		try
		{
			if (!File.Exists("botCmd.txt"))
			{
				return;
			}
			string raw = File.ReadAllText("botCmd.txt");
			if (raw.Length > 0)
			{
				File.WriteAllText("botCmd.txt", "");
			}
			raw = raw.Trim();
			if (raw.Length == 0)
			{
				return;
			}
			string[] parts = raw.Split(' ', StringSplitOptions.RemoveEmptyEntries);

			// Every command answers in cmdResult.txt with ok/fail plus why. Writing
			// the command file is not evidence the game did anything - reporting
			// success on a write alone made sabotage look like it worked when the
			// map entry did not exist. The Python side waits for this reply.
			string result = "fail unknown command";
			switch (parts[0].ToLowerInvariant())
			{
				case "openchat":
					result = BoolResult(SetChatOpen(true));
					break;
				case "say":
					// say <message...>  (everything after the verb is the message)
					if (parts.Length > 1)
					{
						// re-join, because a message can contain multiple spaces
						int firstSpace = raw.IndexOf(' ');
						string msg = firstSpace >= 0 ? raw.Substring(firstSpace + 1) : "";
						result = BoolResult(SendChatMessage(msg));
					}
					else
					{
						result = "fail say needs a message";
					}
					break;
				case "meetingtime":
					float left = MeetingTimeLeft();
					result = left < 0 ? "fail no meeting is running"
						: "ok " + left.ToString("F1");
					break;
				case "closechat":
					result = BoolResult(SetChatOpen(false));
					break;
				case "castvote":
					// castvote <colorIndex>   (-1 = skip)
					if (parts.Length > 1)
					{
						int colorIndex = int.Parse(parts[1]);
						result = BoolResult(CastVoteForColor(colorIndex));
					}
					else
					{
						result = "fail castvote needs a colour index";
					}
					break;
				case "clicksabotage":
					if (parts.Length > 1)
					{
						result = SabotageResult(parts[1]);
					}
					else
					{
						result = "fail clicksabotage needs a name";
					}
					break;
				case "overrule":
					// overrule <playerId>
					if (parts.Length > 1 && int.TryParse(parts[1], out int overruleTarget))
				{
					result = BoolResult(JudgeOverrule(overruleTarget));
				}
				else
				{
					result = "fail overrule needs a playerId";
				}
				break;
				case "opensabotage":
					result = BoolResult(OpenSabotageMap());
					break;
				case "venttravel":
					// venttravel <ventId>
					if (parts.Length > 1)
					{
						result = BoolResult(VentTravelTo(int.Parse(parts[1])));
					}
					else
					{
						result = "fail venttravel needs a vent id";
					}
					break;
				case "useability":
					result = BoolResult(UsePrimaryAbility());
					break;
				case "useability2":
					result = BoolResult(UseSecondaryAbility());
					break;
				case "protect":
					if (parts.Length > 1)
					{
						result = BoolResult(ProtectColor(int.Parse(parts[1])));
					}
					else
					{
						result = "fail protect needs a colour index";
					}
					break;
				case "mimic":
					if (parts.Length > 1)
					{
						result = BoolResult(MimicColor(int.Parse(parts[1])));
					}
					else
					{
						result = "fail mimic needs a colour index";
					}
					break;
				case "minigamecall":
					// minigamecall <method> [int args...]
					// Drives the open task panel through the game's own method
					// for that control, which is what its own button calls.
					if (parts.Length > 1)
					{
						int[] callArgs = new int[parts.Length - 2];
						for (int a = 0; a < callArgs.Length; a++)
						{
							int.TryParse(parts[a + 2], out callArgs[a]);
						}
						result = MinigameCall(parts[1], callArgs);
					}
					else
					{
						result = "fail minigamecall needs a method name";
					}
					break;
			}
			// Reply after the action, including on failure, so the caller is never
			// left waiting on a command the game silently ignored.
			File.WriteAllText("cmdResult.txt", result);
		}
		catch (Exception ex)
		{
			try
			{
				File.WriteAllText("cmdResult.txt", "fail exception " + ex.GetType().Name);
			}
			catch
			{
			}
		}
	}

	// Send a chat message through the game's own RPC, which is the same path the
	// client's own input takes. Typing it with pyautogui needed the chat box open
	// and the text field focused, both of which are timing-sensitive.
	//
	// GameManager also rate-limits chat (ChatController.MAX_CHAT_SEND_RATE), so a
	// refusal here is usually "too fast", and the caller is told so.
	public static bool SendChatMessage(string text)
	{
		try
		{
			if (string.IsNullOrWhiteSpace(text))
			{
				return false;
			}
			// The game caps a single message; sending more gets it rejected.
			if (text.Length > 50)
			{
				text = text.Substring(0, 50);
			}
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null)
			{
				return false;
			}
			// RpcSendChat lives on PlayerControl, not GameManager. It is the same
			// call the client's own chat input ends up making, so the message is
			// indistinguishable from a typed one.
			return lp.RpcSendChat(text);
		}
		catch
		{
			return false;
		}
	}

	// How long is left in the current meeting's discussion, in seconds. The model
	// needs this to budget speaking against voting; without it it either talks
	// until the timer runs out or says nothing at all.
	public static float MeetingTimeLeft()
	{
		try
		{
			MeetingHud hud = MeetingHud.Instance;
			if (hud == null)
			{
				return -1f;
			}
			return hud.discussionTimer;
		}
		catch
		{
			return -1f;
		}
	}

	private static string BoolResult(bool ok)
	{
		return ok ? "ok" : "fail refused";
	}

	// Sabotage gets a real reason, because a bare "refused" is what made this
	// undiagnosable: the caller needs to know whether the name was unknown, the
	// map was never loaded, or the game itself declined.
	private static string SabotageResult(string name)
	{
		try
		{
			SystemTypes target;
			bool isDoor;
			if (!NameToSystem(name, out target, out isDoor))
			{
				return "fail unknown sabotage name " + name;
			}
			var all = FindAll<MapRoom>();
			if (all == null)
			{
				return "fail could not enumerate the sabotage map";
			}
			int usable = 0;
			for (int i = 0; i < all.Length; i++)
			{
				if (all[i] != null)
				{
					usable++;
				}
			}
			if (usable == 0)
			{
				return "fail found " + all.Length +
					   " MapRoom objects but none usable - the sabotage map is not loaded";
			}
			if (!ClickSabotage(name))
			{
				return "fail the game refused " + name + " (" + target + ")";
			}
			return "ok " + target;
		}
		catch (Exception ex)
		{
			return "fail exception " + ex.GetType().Name;
		}
	}

	// MeetingHud.playerStates[0] is the skip button, 1..n are the players in
	// voting order, so we can drive a vote without touching the screen.
	private static bool CastVoteForColor(int colorIndex)
	{
		try
		{
			MeetingHud hud = MeetingHud.Instance;
			if (hud == null)
			{
				return false;
			}
			Il2CppArrayBase<PlayerVoteArea> states = hud.playerStates;
			if (states == null)
			{
				return false;
			}
			if (colorIndex < 0)
			{
				hud.Select(0);
				hud.Confirm(0);
				return true;
			}
			var all = GetAllPlayerControls();
			int wantedClientId = -1;
			for (int i = 0; i < all.Count; i++)
			{
				if (all[i] != null && all[i].Data != null && TranslateColorName(all[i].Data.ColorName) == colorIndex)
				{
					wantedClientId = all[i].PlayerId;
					break;
				}
			}
			if (wantedClientId < 0)
			{
				return false;
			}
			for (int i = 1; i < states.Length; i++)
			{
				PlayerVoteArea area = states[i];
				if (area == null)
				{
					continue;
				}
				if (area.VotedForId == wantedClientId)
				{
					hud.Select(i);
					hud.Confirm((byte)i);
					return true;
				}
			}
			return false;
		}
		catch
		{
			return false;
		}
	}

	// The local player's outstanding tasks, as a plain System List, because
	// PlayerControl.myTasks is an Il2Cpp list and this file's helpers are not.
	private static List<PlayerTask> AllMyTasks()
	{
		var outList = new List<PlayerTask>();
		try
		{
			PlayerControl lp = PlayerControl.LocalPlayer;
			if (lp == null || lp.myTasks == null)
			{
				return outList;
			}
			for (int i = 0; i < lp.myTasks.Count; i++)
			{
				PlayerTask t = lp.myTasks[i];
				if (t != null)
				{
					outList.Add(t);
				}
			}
		}
		catch
		{
		}
		return outList;
	}

	// Full task routes. sendData.txt only carries StartAt, so the bot knew a
		// task began in Cafeteria but not where the panel actually was, and not
		// that Empty Garbage has a second stage in Storage. It was firing solvers
		// at whatever spot it happened to be standing in and reporting success.
		//
		// One line per task: Name|x,y|x,y  in stage order, from PlayerTask.Locations.
		// Written to its own file so the 15-line sendData contract stays intact.
		private static void WriteTaskRoutes(List<PlayerTask> tasks)
		{
			try
			{
				StringBuilder sb = new StringBuilder();
				for (int i = 0; i < tasks.Count; i++)
				{
					PlayerTask t = tasks[i];
					if (t == null)
					{
						continue;
					}
					sb.Append(TranslateTaskTypes(t.TaskType));
					try
					{
						// PlayerTask.Locations is one position per stage, in order.
						for (int s = 0; s < t.Locations.Count; s++)
						{
							Vector2 p = t.Locations[s];
							sb.Append("|").Append(Math.Round(p.x, 2)).Append(",")
							  .Append(Math.Round(p.y, 2));
						}
					}
					catch
					{
					}
					sb.Append(Environment.NewLine);
				}
			WriteAtomic("taskRoutes.txt", sb.ToString());
		}
		catch
		{
		}
	}

	// Screen position of UI elements, in client-area pixels with a top-left
	// origin (i.e. directly usable as pyautogui coordinates once the window
	// origin is added). Derived from the game's own transforms, so it stays
	// correct at any resolution.
	private static void WriteUiCoords()
	{
		try
		{
			Camera cam = Camera.main;
			if (cam == null)
			{
				return;
			}
			float h = Screen.height;
			string text = "";

			// in-game chat toggle
			try
			{
				HudManager hudMgr = HudManager.Instance;
				if (hudMgr != null && hudMgr.Chat != null && hudMgr.Chat.IsOpenOrOpening)
				{
					text += "chatopen 1\n";
				}
				else
				{
					text += "chatopen 0\n";
				}
			}
			catch
			{
			}

			// meeting vote buttons
			MeetingHud hud = MeetingHud.Instance;
			if (hud != null)
			{
				try
				{
					Il2CppArrayBase<PlayerVoteArea> states = hud.playerStates;
					if (states != null)
					{
						for (int i = 0; i < states.Length; i++)
						{
							PlayerVoteArea area = states[i];
							if (area == null || area.PlayerButton == null)
							{
								continue;
							}
							Vector3 p = cam.WorldToScreenPoint(area.transform.position);
							text += "vote " + i + " " + (int)p.x + " " + (int)(h - p.y) + "\n";
						}
					}
				}
				catch
				{
				}
			}
			WriteAtomic("uiCoords.txt", text);
		}
		catch
		{
		}
	}

	private static bool inGameFlag;

	// The Python side does a bare open() on inGameData.txt, so this file must always exist.
	// PlayerControl.OnGameStart is not invoked in current game builds, so the round state is
	// derived from the data snapshot instead.
	public static void SetInGame(bool value)
	{
		if (inGameFlag == value)
		{
			return;
		}
		inGameFlag = value;
		try
		{
			File.WriteAllText("inGameData.txt", value ? "1" : "0");
		}
		catch
		{
		}
	}

	public const string Id = "AmongUsAI";

	public Harmony Harmony { get; } = new Harmony("AmongUsAI");

	public ConfigEntry<string> ConfigName { get; private set; }

	public static string Name => "AmongUsAI";

	public static string Version => "1.0.0-dev";

	public override void Load()
	{
		ConfigName = ((BasePlugin)this).Config.Bind<string>("Fake", "Name", ":>", (ConfigDescription)null);
		Harmony.PatchAll();
	}

	public static int TranslateColorName(string colorName)
	{
		if (colorName == null)
		{
			return -1;
		}
		colorName = colorName.ToUpper().Replace("(", "").Replace(")", "");
		string[] array = new string[18]
		{
			"RED", "BLUE", "GREEN", "PINK", "ORANGE", "YELLOW", "BLACK", "WHITE", "PURPLE", "BROWN",
			"CYAN", "LIME", "MAROON", "ROSE", "BANANA", "GRAY", "TAN", "CORAL"
		};
		return Array.IndexOf(array, colorName.ToUpper());
	}

	public static Il2CppSystem.Collections.Generic.List<PlayerControl> GetAllPlayerControls()
	{
		return PlayerControl.AllPlayerControls;
	}

	public static List<NetworkedPlayerInfo> GetAllPlayerData()
	{
		List<NetworkedPlayerInfo> result = new List<NetworkedPlayerInfo>();
		var allPlayerControls = GetAllPlayerControls();
		for (int i = 0; i < allPlayerControls.Count; i++)
		{
			PlayerControl current = allPlayerControls[i];
			if (current == null || current.Data == null)
			{
				continue;
			}
			result.Add(current.Data);
		}
		return result;
	}
}
