using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using AssetRipper.Primitives;
using Cpp2IL.Core;
using Cpp2IL.Core.Model.Contexts;
using LibCpp2IL;

// Dump the ISIL of a named list of types straight out of the local game.
//
// The dump.cs in tools/dump only carries signatures - Il2CppDumper gives you the
// shape of a class, not what it DOES. For a minigame that is exactly what you
// are missing: knowing that SimonSaysGame has a Queue<int> called operations
// is not the same as knowing when it enqueues, and when. Cpp2IL recovers the
// method bodies as IL from GameAssembly.dll, which is the game's own code, so
// nothing here is guessed.
class D
{
    static int Main(string[] args)
    {
        string gdir = @"C:\Games\Among Us";
        string pe = Path.Combine(gdir, "GameAssembly.dll");
        string meta = Path.Combine(gdir, "Among Us_Data", "il2cpp_data", "Metadata",
                                   "global-metadata.dat");

        string[] want = args.Length > 1
            ? args[1].Split(',', StringSplitOptions.RemoveEmptyEntries)
            : new[] { "SimonSaysGame", "SweepMinigame", "SampleMinigame" };

        Console.WriteLine("loading metadata + binary...");
        UnityVersion uv = new UnityVersion(2022, 3, 44);
        if (!LibCpp2IlMain.LoadFromFile(pe, meta, uv))
        {
            Console.WriteLine("LOAD FAILED");
            return 1;
        }
        Console.WriteLine("metadata version " + LibCpp2IlMain.MetadataVersion);

        // The x64 handler has to be registered before the analysis context is
        // built, or it cannot decode a single instruction.
        Cpp2IL.Core.Api.InstructionSetRegistry.RegisterInstructionSet<
            Cpp2IL.Core.InstructionSets.X86InstructionSet>(
            LibCpp2IL.DefaultInstructionSets.X86_64);

        ApplicationAnalysisContext ctx =
            new ApplicationAnalysisContext(LibCpp2IlMain.Binary!, LibCpp2IlMain.TheMetadata!);
        Console.WriteLine("analysis context built: " + ctx.Assemblies.Count + " assemblies");

        bool raw = args.Length > 2 && args[2] == "--raw";

        var sb = new StringBuilder();
        int typesFound = 0, methodsFound = 0, failed = 0;

        foreach (AssemblyAnalysisContext asm in ctx.Assemblies)
        {
            foreach (TypeAnalysisContext t in asm.Types)
            {
                if (Array.IndexOf(want, t.Name) < 0 && Array.IndexOf(want, t.FullName) < 0) continue;
                typesFound++;
                sb.AppendLine("==== TYPE " + t.FullName);
                foreach (MethodAnalysisContext m in t.Methods)
                {
                    sb.AppendLine("-- " + m.FullName);
                    methodsFound++;
                    if (raw)
                    {
                        try
                        {
                            m.EnsureRawBytes();
                            byte[] bytes = m.RawBytes.ToArray();
                            var reader = new Iced.Intel.ByteArrayCodeReader(bytes);
                            var decoder = Iced.Intel.Decoder.Create(64, reader, m.UnderlyingPointer);
                            Iced.Intel.Instruction instr;
                            int guard = 0;
                            do
                            {
                                instr = decoder.Decode();
                                if (instr.Code == Iced.Intel.Code.INVALID) break;
                                sb.AppendLine("   " + instr.IP.ToString("X")
                                    + "  " + instr.ToString());
                            } while (++guard < 4000);
                        }
                        catch (Exception e)
                        {
                            failed++;
                            sb.AppendLine("   ## RAW FAILED " + e.GetType().Name + ": " + e.Message);
                        }
                        continue;
                    }
                    try
                    {
                        m.Analyze();
                    }
                    catch (Exception e)
                    {
                        failed++;
                        sb.AppendLine("   ## ANALYSIS FAILED " + e.GetType().Name + ": " + e.Message);
                        continue;
                    }
                    List<Cpp2IL.Core.ISIL.InstructionSetIndependentInstruction> isil = m.ConvertedIsil;
                    if (isil == null || isil.Count == 0)
                    {
                        sb.AppendLine("   (no IL recovered)");
                        continue;
                    }
                    foreach (var i in isil)
                    {
                        sb.AppendLine("   " + i.ToString());
                    }
                }
            }
        }

        string outPath = args.Length > 0 ? args[0] : "minigames.il.txt";
        File.WriteAllText(outPath, sb.ToString());
        Console.WriteLine($"types {typesFound} methods {methodsFound} failed {failed}");
        Console.WriteLine("wrote " + outPath + " (" + new FileInfo(outPath).Length + " bytes)");
        return 0;
    }
}
