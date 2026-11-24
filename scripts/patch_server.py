from pathlib import Path

def replace_once(path, old, new, label):
    p = Path(path)
    source = p.read_text()
    if new in source:
        print(f"{label}: already applied")
        return
    if old not in source:
        raise SystemExit(f"{label}: source anchor not found")
    p.write_text(source.replace(old, new, 1))
    print(f"{label}: applied")

# Keep SXB clients connected while their server-side PlayerControl is initialized.
p = Path("src/Impostor.Server/Net/State/ClientPlayer.cs")
s = p.read_text()
if "Retaining SXB bot" not in s:
    start = s.index("if (Character == null)", s.index("private async void RunSpawnTimeout"))
    brace = s.index("{", start)
    depth = 0
    end = None
    for i in range(brace, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit("Unbalanced RunSpawnTimeout block")
    replacement = '''if (Character == null)
                  {
                      if (Client.Name is "SXBWatcher" or "BMGmonke?!")
                      {
                          _logger.LogInformation("{0} - Retaining SXB bot {1} ({2}) without Unity PlayerControl.", Game.Code, Client.Name, Client.Id);
                      }
                      else
                      {
                          _logger.LogInformation("{0} - Player {1} spawn timed out, kicking.", Game.Code, Client.Id);
                          await KickAsync();
                      }
                  }'''
    p.write_text(s[:start] + replacement + s[end:])

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerPlayerControl.cs",
    '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }''',
    '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            if (initialState) writer.Write(IsNew);
            writer.Write(PlayerId);
            return new ValueTask<bool>(true);
        }''',
    "PlayerControl serializer")

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerPlayerControl.cs",
    "        public byte PlayerId { get; private set; }",
    """        public byte PlayerId { get; private set; }

        internal void InitializeForServer(byte playerId)
        {
            IsNew = true;
            PlayerId = playerId;
        }""",
    "PlayerControl initializer")

p = Path("src/Impostor.Server/Net/Inner/Objects/Components/InnerPlayerPhysics.cs")
s = p.read_text()
old = '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }'''
new = '''        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }'''
if new not in s:
    if old not in s: raise SystemExit("PlayerPhysics serializer anchor missing")
    s = s.replace(old, new, 1)
old = '''        public override ValueTask DeserializeAsync(IClientPlayer sender, IClientPlayer? target, IMessageReader reader, bool initialState)
        {
            throw new NotImplementedException();
        }'''
new = '''        public override ValueTask DeserializeAsync(IClientPlayer sender, IClientPlayer? target, IMessageReader reader, bool initialState)
        {
            return default;
        }'''
if new not in s:
    if old not in s: raise SystemExit("PlayerPhysics deserializer anchor missing")
    s = s.replace(old, new, 1)
p.write_text(s)

p = Path("src/Impostor.Server/Net/State/Game.Outgoing.cs")
s = p.read_text()
old = "                writer.WritePacked(obj.NetId);"
new = "                writer.WritePacked(component.NetId);"
if new not in s:
    if old not in s: raise SystemExit("Spawn component NetId anchor missing")
    p.write_text(s.replace(old, new, 1))

p = Path("src/Impostor.Server/Net/State/Game.Data.cs")
s = p.read_text()
old = """            await SendObjectSpawnAsync(playerInfo);
        }

        private async ValueTask DespawnPlayerInfoAsync"""
new = """            var sxbMode = Host?.Client.Name == "BMGmonke?!" || sender.Client.Name is "SXBWatcher" or "BMGmonke?!";
            // PlayerInfo is the lobby roster entry. Broadcast it to every
            // connected lobby member, including clients whose Scene has not
            // reached OnlineGame yet; filtering by Scene can make a joined bot
            // invisible to the host during lobby synchronization.
            await SendObjectSpawnAsync(playerInfo);
            if (sxbMode)
            {
                _logger.LogInformation(
                    "Published server-side PlayerInfo for {Name} (client {ClientId}, player {PlayerId}) to all lobby members; host-authoritative={HostAuthoritative}.",
                    sender.Client.Name,
                    sender.Client.Id,
                    playerInfo.PlayerId,
                    IsHostAuthoritive);
            }

            if (sender.Client.Name is "SXBWatcher" or "BMGmonke?!" || Host?.Client.Name == "BMGmonke?!")
            {
                await SpawnSxbPlayerControlAsync(sender, playerInfo);
            }
        }

        private async ValueTask SpawnSxbPlayerControlAsync(ClientPlayer sender, InnerPlayerInfo playerInfo)
        {
            var control = (InnerPlayerControl)ActivatorUtilities.CreateInstance(_serviceProvider, typeof(InnerPlayerControl), this);
            control.InitializeForServer(playerInfo.PlayerId);
            control.SpawnFlags = SpawnFlags.None;
            foreach (var component in control.GetComponentsInChildren<InnerNetObject>())
            {
                component.NetId = _nextNetId++;
                component.OwnerId = sender.Client.Id;
                if (!AddNetObject(component))
                {
                    throw new InvalidOperationException($"Could not register SXB player component {component.GetType().Name}.");
                }
                await OnSpawnAsync(sender, component);
            }

            // The fake host has no Unity client to calculate its initial spawn
            // transform. Give every SXB-created player the map's real spawn point
            // before its NetworkTransform is serialized to joining clients.
            if (GameNet.ShipStatus is { } shipStatus)
            {
                await control.NetworkTransform.SetPositionAsync(
                    sender,
                    shipStatus.GetSpawnLocation(control, PlayerCount, true));
            }

            // Deliver immediately only to clients already in OnlineGame.
            // Lobby clients receive this object later through SyncServerObjectsAsync.
            await SendObjectSpawnAsync(control, sender.Client.Id);
            foreach (var existing in _players.Values.Where(
                player => player.Client.Id != sender.Client.Id && player.Scene == "OnlineGame"))
            {
                await SendObjectSpawnAsync(control, existing.Client.Id);
            }

            _logger.LogInformation("Spawned server-side PlayerControl for {Name}, player ID {PlayerId} at {Position}.", sender.Client.Name, playerInfo.PlayerId, control.NetworkTransform.Position);
        }

        private async ValueTask DespawnPlayerInfoAsync"""
if "SpawnSxbPlayerControlAsync" not in s:
    if old not in s: raise SystemExit("PlayerInfo spawn insertion point missing")
    p.write_text(s.replace(old, new, 1))

print("SXB server spawn patch complete")


# Give SXB-created PlayerInfo objects a complete, non-placeholder outfit.
replace_once(
    "src/Impostor.Api/Innersloth/Customization/PlayerOutfit.cs",
    "            internal set => SetField(ref _playerName, value);",
    "            set => SetField(ref _playerName, value);",
    "PlayerOutfit name setter")
replace_once(
    "src/Impostor.Api/Innersloth/Customization/PlayerOutfit.cs",
    "            internal set => SetField(ref _color, value);",
    "            set => SetField(ref _color, value);",
    "PlayerOutfit color setter")

replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """            playerInfo.ClientId = sender.Client.Id;
            playerInfo.FriendCode = sender.Client.FriendCode;""",
    """            playerInfo.ClientId = sender.Client.Id;
            playerInfo.CurrentOutfit.PlayerName = sender.Client.Name;
            // The public-lobby watcher has a fixed identity: Blue, even if
            // another player already selected Blue. This is assigned directly
            // by the server before PlayerInfo is spawned, bypassing client color
            // availability checks; the server remains authoritative.
            var isSxbWatcher = sender.Client.Name == "SXBWatcher";
            if (isSxbWatcher)
            {
                // Lock only the watcher. Leave real clients' colors untouched
                // until their own SetColor RPC is processed.
                playerInfo.CurrentOutfit.Color = Impostor.Api.Innersloth.Customization.ColorType.Blue;
            }
            playerInfo.CurrentOutfit.HatId = isSxbWatcher ? "hat_TopHat" : "hat_NoHat";
            playerInfo.CurrentOutfit.PetId = "pet_EmptyPet";
            playerInfo.CurrentOutfit.SkinId = "skin_None";
            playerInfo.CurrentOutfit.VisorId = "visor_EmptyVisor";
            playerInfo.CurrentOutfit.NamePlateId = "nameplate_NoPlate";
            playerInfo.FriendCode = sender.Client.FriendCode;""",
    "SXB PlayerInfo identity")

# The protocol-only host must publish the map and game-manager net objects;
# otherwise clients enter OnlineGame without a ship and remain in a void.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/ShipStatus/InnerShipStatus.cs",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }""",
    "ShipStatus spawn serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/GameManager/InnerGameManager.cs",
    """    public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        throw new System.NotImplementedException();
    }""",
    """    public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        return new ValueTask<bool>(false);
    }""",
    "GameManager spawn serializer")

p = Path("src/Impostor.Server/Net/State/Game.Data.cs")
s = p.read_text()
anchor = """                        sender.Scene = scene;

                        _logger.LogTrace("> Scene {0} to {1}", clientId, sender.Scene);

                        await SyncServerObjectsAsync(sender);"""
replacement = """                        sender.Scene = scene;

                        _logger.LogTrace("> Scene {0} to {1}", clientId, sender.Scene);

                        await EnsureSxbWorldObjectsAsync(sender);
                        await SyncServerObjectsAsync(sender);"""
if "EnsureSxbWorldObjectsAsync" not in s:
    if anchor not in s: raise SystemExit("SceneChange world-object insertion anchor missing")
    s = s.replace(anchor, replacement, 1)
    marker = """        private async ValueTask SyncServerObjectsAsync(ClientPlayer sender)
        {"""
    method = """        private async ValueTask EnsureSxbWorldObjectsAsync(ClientPlayer sender)
        {
            if (Host?.Client.Name != "BMGmonke?!" && sender.Client.Name is not ("SXBWatcher" or "BMGmonke?!"))
            {
                return;
            }

            // Ensure the Dropship lobby's map is selected before choosing
            // the ShipStatus prefab. LogicOptions may not have deserialized yet
            // when the first SXB client enters OnlineGame.
            Options.Map = MapTypes.Polus;

            if (!_allObjects.Values.OfType<InnerShipStatus>().Any())
            {
                // Match the network ShipStatus prefab to the now-authoritative map.
                var shipType = Options.Map switch
                {
                    MapTypes.Skeld => typeof(InnerSkeldShipStatus),
                    MapTypes.MiraHQ => typeof(InnerMiraShipStatus),
                    MapTypes.Polus => typeof(InnerPolusShipStatus),
                    MapTypes.Dleks => typeof(InnerDleksShipStatus),
                    MapTypes.Airship => typeof(InnerAirshipStatus),
                    MapTypes.Fungle => typeof(InnerFungleShipStatus),
                    _ => typeof(InnerSkeldShipStatus),
                };
                var ship = (InnerShipStatus)ActivatorUtilities.CreateInstance(_serviceProvider, shipType, this);
                ship.SpawnFlags = SpawnFlags.None;
                ship.NetId = _nextNetId++;
                ship.OwnerId = ServerOwned;
                if (!AddNetObject(ship))
                {
                    throw new InvalidOperationException("Could not register the SXB Skeld ship object.");
                }
                await OnSpawnAsync(sender, ship);
                foreach (var existing in _players.Values.Where(
                    player => player.Client.Id != sender.Client.Id && player.Scene == "OnlineGame"))
                {
                    await SendObjectSpawnAsync(ship, existing.Client.Id);
                }
                _logger.LogInformation("Published {Map} ship object for SXB lobby {Code}.", Options.Map, Code);
            }

            // Do not create InnerNormalGameManager while the client is entering
            // the pre-game lobby. The real client creates/receives game-manager
            // state as part of game start; publishing it during lobby scene load
            // can advance the client into an uninitialized gameplay state.
            _logger.LogInformation("Deferred normal game manager until game start for SXB lobby {Code}.", Code);
        }

"""
    if marker not in s: raise SystemExit("SyncServerObjects method insertion point missing")
    s = s.replace(marker, method + marker, 1)
    p.write_text(s)

print("SXB map/player initialization patch complete")

# The watcher is a general public-lobby bot, not an English/free-chat-only
# client. Treat uint.MaxValue as a wildcard language value in the filtered
# listing API; all ordinary language filters retain their exact-match behavior.
replace_once(
    "src/Impostor.Server/Http/ListingManager.cs",
    """if (filter.SubFilter is LanguageFilter langFilter && game.Options.Keywords != (GameKeywords)langFilter.AcceptedValues)""",
    """if (filter.SubFilter is LanguageFilter langFilter && langFilter.AcceptedValues != uint.MaxValue && game.Options.Keywords != (GameKeywords)langFilter.AcceptedValues)""",
    "SXB watcher all-language lobby discovery")


# The watcher starts with its own local cosmetic selection and may send a
# SetHatStr RPC after joining. Keep the server-authoritative top hat instead
# of allowing that client preference to overwrite the forced outfit.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerPlayerControl.cs",
    """            else
            {
                PlayerInfo.CurrentOutfit.HatId = hat;
                PlayerInfo.CurrentOutfit.HatSequenceId = nextRpcSequenceId;
            }

            return true;
        }

        private async ValueTask<bool> HandleSetSkin""",
    """            else if (sender.Client.Name == "SXBWatcher")
            {
                // The watcher is locked to the SXB uniform. Ignore its local
                // cosmetic loadout RPC so the PlayerInfo top hat stays intact.
                PlayerInfo.CurrentOutfit.HatId = "hat_TopHat";
                return false;
            }
            else
            {
                PlayerInfo.CurrentOutfit.HatId = hat;
                PlayerInfo.CurrentOutfit.HatSequenceId = nextRpcSequenceId;
            }

            return true;
        }

        private async ValueTask<bool> HandleSetSkin""",
    "SXBWatcher forced top hat RPC")


# Serialize the actual Skeld systems and normal-game options. Empty spawn
# payloads leave clients with a ShipStatus shell but no initialized systems.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/ShipStatus/InnerShipStatus.cs",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }""",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            foreach (var system in _systems)
            {
                writer.StartMessage((byte)system.Key);
                system.Value.Serialize(writer, initialState);
                writer.EndMessage();
            }

            return new ValueTask<bool>(true);
        }""",
    "ShipStatus system-state serializer")

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/GameManager/Logic/GameLogicComponent.cs",
    """    public virtual ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        throw new NotImplementedException();
    }""",
    """    public virtual ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        return ValueTask.FromResult(true);
    }""",
    "Game logic empty-state serializer")

replace_once(
    "src/Impostor.Server/Net/Inner/Objects/GameManager/InnerGameManager.cs",
    """    public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        return new ValueTask<bool>(false);
    }""",
    """    public override async ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
    {
        for (var i = 0; i < _logicComponents.Count; i++)
        {
            writer.StartMessage((byte)i);
            await _logicComponents[i].SerializeAsync(writer, initialState);
            writer.EndMessage();
        }

        return true;
    }""",
    "GameManager logic-state serializer")





# The upstream server intentionally leaves several system serializers
# unimplemented. Calling them from ShipStatus.SerializeAsync throws at runtime,
# preventing the ShipStatus SpawnFlag from reaching clients. Supply valid
# initial-state payloads for the systems used by Polus (and the common Skeld
# systems) so the map object can actually be transmitted.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/SwitchSystem.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write(ExpectedSwitches);
            writer.Write(ActualSwitches);
            writer.Write(Value);
        }""",
    "SwitchSystem serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/MedScanSystem.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.WritePacked(UsersList.Count);
            foreach (var playerId in UsersList)
            {
                writer.Write(playerId);
            }
        }""",
    "MedScanSystem serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/DoorsSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write((byte)_timers.Count);
            foreach (var timer in _timers)
            {
                writer.Write((byte)timer.Key);
                writer.Write(timer.Value);
            }

            for (var i = 0; i < _doors.Count; i++)
            {
                writer.Write(_doors[i]);
            }
        }""",
    "DoorsSystemType serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/HudOverrideSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write(IsActive);
        }""",
    "HudOverrideSystemType serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/SecurityCameraSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write(InUse);
        }""",
    "SecurityCameraSystemType serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/ReactorSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write(Countdown);
            writer.WritePacked(UserConsolePairs.Count);
            foreach (var pair in UserConsolePairs)
            {
                writer.Write(pair.Item1);
                writer.Write(pair.Item2);
            }
        }""",
    "ReactorSystemType serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/SabotageSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write(Timer);
        }""",
    "SabotageSystemType serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/LifeSuppSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            writer.Write(Countdown);
            writer.WritePacked(CompletedConsoles.Count);
            foreach (var console in CompletedConsoles)
            {
                writer.WritePacked(console);
            }
        }""",
    "LifeSuppSystemType serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/Systems/ShipStatus/AutoDoorsSystemType.cs",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public void Serialize(IMessageWriter writer, bool initialState)
        {
            if (initialState)
            {
                for (var i = 0; i < _doors.Count; i++)
                {
                    writer.Write(_doors[i]);
                }
            }
            else
            {
                var mask = _doors.Count >= 32 ? uint.MaxValue : (1u << _doors.Count) - 1u;
                writer.WritePacked(mask);
                for (var i = 0; i < _doors.Count && i < 32; i++)
                {
                    writer.Write(_doors[i]);
                }
            }
        }""",
    "AutoDoorsSystemType serializer")

# The original loop checks the new dictionary's Count (always zero), not the
# map data's door count, so no door state entries are ever initialized.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/ShipStatus/InnerShipStatus.cs",
    "            for (var i = 0; i < Doors.Count; i++)",
    "            for (var i = 0; i < Data.Doors.Count; i++)",
    "ShipStatus door initialization")

# Late joiners must receive the fake host's PlayerControl too. The original
# server sync only retransmits ServerOwned objects, while SXB PlayerControls
# retain the fake client's owner ID. Sync the SXB root control (not its child
# components) after the map and PlayerInfo dependencies.
replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """        private async ValueTask SyncServerObjectsAsync(ClientPlayer sender)
        {
            foreach (var obj in _allObjects.Values)
            {
                if (obj.OwnerId == ServerOwned)
                {
                    _logger.LogTrace("Syncing {Type} {NetId}", obj.GetType(), obj.NetId);
                    await SendObjectSpawnAsync(obj, sender.Client.Id);
                }
            }
        }""",
    """        private async ValueTask SyncServerObjectsAsync(ClientPlayer sender)
        {
            var objects = _allObjects.Values
                .Where(obj =>
                    obj.OwnerId == ServerOwned ||
                    (obj is InnerPlayerControl control &&
                     control.OwnerId != sender.Client.Id &&
                     (Host?.Client.Name == "BMGmonke?!" ||
                      (TryGetPlayer(control.OwnerId, out var owner) &&
                       owner.Client.Name is "BMGmonke?!" or "SXBWatcher"))))
                .OrderBy(obj => obj switch
                {
                    InnerShipStatus => 0,
                    InnerGameManager => 1,
                    InnerPlayerInfo => 2,
                    InnerPlayerControl => 3,
                    _ => 4,
                })
                .ToArray();

            foreach (var obj in objects)
            {
                _logger.LogInformation(
                    "Syncing {Type} {NetId} (owner {OwnerId}) to {PlayerName} ({ClientId}).",
                    obj.GetType().Name,
                    obj.NetId,
                    obj.OwnerId,
                    sender.Client.Name,
                    sender.Client.Id);
                await SendObjectSpawnAsync(obj, sender.Client.Id);
            }
        }""",
    "SXB late-join object synchronization")


# Every child InnerNetObject has its own NetId. Repeating the prefab root's
# NetId causes the client to reject PlayerPhysics and NetworkTransform as
# duplicate objects, leaving the remote player with a broken render/movement.
replace_once(
    "src/Impostor.Server/Net/State/Game.Outgoing.cs",
    """                writer.WritePacked(obj.NetId);
                writer.StartMessage(1);""",
    """                writer.WritePacked(component.NetId);
                writer.StartMessage(1);""",
    "SXB child component NetIds")

# A bot host exists before any human joins. Its PlayerControl must therefore
# be marked as an existing player when serialized to later joiners.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerPlayerControl.cs",
    """        internal void InitializeForServer(byte playerId)
        {
            IsNew = true;
            PlayerId = playerId;
        }""",
    """        internal void InitializeForServer(byte playerId)
        {
            IsNew = true;
            PlayerId = playerId;
        }

        internal void MarkAsExisting()
        {
            IsNew = false;
        }""",
    "SXB PlayerControl existing-state marker")

replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """            foreach (var existing in _players.Values.Where(
                player => player.Client.Id != sender.Client.Id && player.Scene == "OnlineGame"))
            {
                await SendObjectSpawnAsync(control, existing.Client.Id);
            }

            _logger.LogInformation("Spawned server-side PlayerControl""",
    """            foreach (var existing in _players.Values.Where(
                player => player.Client.Id != sender.Client.Id && player.Scene == "OnlineGame"))
            {
                await SendObjectSpawnAsync(control, existing.Client.Id);
            }

            control.MarkAsExisting();
            _logger.LogInformation("Spawned server-side PlayerControl""",
    "SXB PlayerControl late-join state")


# Preserve the upstream InnerCustomNetworkTransform initial-state wire format.

# Among Us creates each joining player's character prefab with the
# IsClientCharacter spawn flag. Without it, clients may register the network
# object but fail to initialize the visible/local character graph correctly.
replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """            control.InitializeForServer(playerInfo.PlayerId);
            control.SpawnFlags = SpawnFlags.None;""",
    """            control.InitializeForServer(playerInfo.PlayerId);
            control.SpawnFlags = SpawnFlags.IsClientCharacter;""",
    "SXB player character spawn flag")


# A normal OnlineGame lobby also needs its LobbyBehaviour object. The Unity
# LobbyBehaviour owns the Dropship lobby presentation and is passed into
# PlayerPhysics.CoSpawnPlayer; omitting it leaves clients with a character
# over a blank scene and breaks the spawn animation.
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerLobbyBehaviour.cs",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public override ValueTask<bool> SerializeAsync(IMessageWriter writer, bool initialState)
        {
            return new ValueTask<bool>(false);
        }""",
    "LobbyBehaviour empty serializer")
replace_once(
    "src/Impostor.Server/Net/Inner/Objects/InnerLobbyBehaviour.cs",
    """        public override ValueTask DeserializeAsync(IClientPlayer sender, IClientPlayer? target, IMessageReader reader, bool initialState)
        {
            throw new NotImplementedException();
        }""",
    """        public override ValueTask DeserializeAsync(IClientPlayer sender, IClientPlayer? target, IMessageReader reader, bool initialState)
        {
            return default;
        }""",
    "LobbyBehaviour empty deserializer")

replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """            if (!_allObjects.Values.OfType<InnerShipStatus>().Any())
            {""",
    """            if (!_allObjects.Values.OfType<InnerLobbyBehaviour>().Any())
            {
                var lobby = (InnerLobbyBehaviour)ActivatorUtilities.CreateInstance(
                    _serviceProvider, typeof(InnerLobbyBehaviour), this);
                lobby.SpawnFlags = SpawnFlags.None;
                lobby.NetId = _nextNetId++;
                lobby.OwnerId = ServerOwned;
                if (!AddNetObject(lobby))
                {
                    throw new InvalidOperationException("Could not register the SXB lobby behaviour.");
                }
                await OnSpawnAsync(sender, lobby);
                foreach (var existing in _players.Values.Where(
                    player => player.Client.Id != sender.Client.Id && player.Scene == "OnlineGame"))
                {
                    await SendObjectSpawnAsync(lobby, existing.Client.Id);
                }
                _logger.LogInformation("Published lobby behaviour for SXB lobby {Code}.", Code);
            }

            if (!_allObjects.Values.OfType<InnerShipStatus>().Any())
            {""",
    "SXB lobby behaviour spawn")

replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """                    InnerShipStatus => 0,
                    InnerGameManager => 1,
                    InnerPlayerInfo => 2,
                    InnerPlayerControl => 3,
                    _ => 4,""",
    """                    InnerLobbyBehaviour => 0,
                    InnerShipStatus => 1,
                    InnerGameManager => 2,
                    InnerPlayerInfo => 3,
                    InnerPlayerControl => 4,
                    _ => 5,""",
    "SXB lobby object synchronization order")

# GameManager's LogicOptions deserializer writes directly into Game.Options.
# GameData DataFlag packets are not inherently host-only, so a joining watcher
# can otherwise overwrite the host's selected map with its local default (Skeld).
replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """                        if (_allObjects.TryGetValue(netId, out var obj))
                        {
                            await obj.DeserializeAsync(sender, target, reader, false);
                        }""",
    """                        if (_allObjects.TryGetValue(netId, out var obj))
                        {
                            if (obj is InnerGameManager && (!sender.IsHost || sender.Client.Name == "SXBWatcher"))
                            {
                                _logger.LogWarning(
                                    "{PlayerName} ({ClientId}) attempted to update host-authoritative game options; ignoring.",
                                    sender.Client.Name,
                                    sender.Client.Id);
                                break;
                            }

                            await obj.DeserializeAsync(sender, target, reader, false);
                        }""",
    "Reject non-host GameManager option updates")



# Host-authoritative public lobbies do not let the server create ordinary
# PlayerInfo objects. SXBWatcher is protocol-only and cannot create its own
# Unity PlayerInfo, so explicitly allow the server to create it for this bot.
replace_once(
    "src/Impostor.Server/Net/State/Game.Data.cs",
    """            // Hosts spawn PlayerInfo objects if they requested authority
            if (IsHostAuthoritive)
            {
                return;
            }""",
    """            // Hosts spawn PlayerInfo objects if they requested authority.
            // SXBWatcher is protocol-only and cannot create its own Unity object.
            if (IsHostAuthoritive && sender.Client.Name is not ("SXBWatcher" or "BMGmonke?!"))
            {
                return;
            }""",
    "SXB PlayerInfo in host-authoritative lobbies")

// SXBWatcher runs on the same machine as the server. Let this loopback-only
// watcher enumerate every public, joinable lobby without normal preference,
// compatibility, language, map, chat-mode, or mod filters. This affects only
// the listing response; normal game and anti-cheat validation remain enabled.
replace_once(
    "src/Impostor.Server/Http/ListingManager.cs",
    """    public IEnumerable<IGame> FindListingsV2(HttpContext ctx, GameFiltersList filtersList, int maxListings = 10)
    {
        if (filtersList == null || filtersList.FilterSets.Count == 0)""",
    """    public IEnumerable<IGame> FindListingsV2(HttpContext ctx, GameFiltersList filtersList, int maxListings = 10)
    {
        if (ctx.Connection.RemoteIpAddress?.IsLoopback == true &&
            ctx.Request.Headers.TryGetValue("X-SXB-Watcher", out var watcherHeader) &&
            watcherHeader == "SXBWatcher-local-listing")
        {
            return _gameManager.Games
                .Where(game => game.IsPublic &&
                               game.GameState == GameStates.NotStarted &&
                               game.PlayerCount < game.Options.MaxPlayers)
                .Take(maxListings)
                .ToArray();
        }

        if (filtersList == null || filtersList.FilterSets.Count == 0)""",
    "SXBWatcher loopback public-lobby listing access")
