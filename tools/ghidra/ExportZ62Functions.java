// Targeted read-only-byte analysis of the original Z62 module.
// @category NikonZ62
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.lang.Register;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.FlowOverride;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.RefType;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ExportZ62Functions extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException("Output directory and function addresses required");
        }
        Path output = Path.of(args[0]);
        int firstFunction = 1;
        long baseNumber = 0x10020000L;
        if (args[1].startsWith("base:")) {
            baseNumber = Long.parseUnsignedLong(args[1].substring(5), 16);
            firstFunction = 2;
        }
        if ((baseNumber != 0x10020000L && baseNumber != 0x08000000L) || args.length <= firstFunction) {
            throw new IllegalArgumentException("Unsupported module base or missing functions");
        }
        boolean controller = baseNumber == 0x08000000L;
        Address base = toAddr(baseNumber);
        if (!currentProgram.getImageBase().equals(base)) {
            currentProgram.setImageBase(base, true);
        }
        if (!currentProgram.getMinAddress().equals(base) ||
                !currentProgram.getLanguageID().toString().equals("ARM:LE:32:v7")) {
            throw new IllegalStateException("Unexpected raw module language/base");
        }
        Register thumb = currentProgram.getLanguage().getRegister("TMode");
        if (thumb == null) {
            throw new IllegalStateException("ARM Thumb context register not available");
        }
        // This input is an immutable ROM member; RAM objects referenced by it
        // are not initialized here. Read-only ROM permits literal propagation.
        for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
            block.setWrite(false);
            block.setExecute(true);
        }
        // These observed ASIC register windows must be volatile. Otherwise
        // decompilation deletes ISR read-then-write acknowledgements as redundant
        // RAM stores, hiding the actual W1C protocol present in the instructions.
        long[][] ioWindows = controller
            ? new long[][] {{0x40000000L, 0x30000L}, {0x50060000L, 0x1000L}, {0xe000e000L, 0x2000L}}
            : new long[][] {{0x20068000L, 0x4000L}, {0x20100000L, 0x10000L},
                            {0x20380000L, 0x10000L}, {0x203c0000L, 0x10000L}};
        for (long[] window : ioWindows) {
            MemoryBlock io = currentProgram.getMemory().createUninitializedBlock(
                "z62_mmio_" + Long.toHexString(window[0]), toAddr(window[0]), window[1], false);
            io.setRead(true);
            io.setWrite(true);
            io.setExecute(false);
            io.setVolatile(true);
        }
        StringBuilder index = new StringBuilder("address\tfunction\tcompleted\tmessage\n");
        // Set all selected Thumb contexts before any disassembly creates code
        // units. Ghidra forbids changing context through existing instructions.
        for (int i = firstFunction; i < args.length; i++) {
            long number = Long.parseUnsignedLong(args[i].replace("0x", ""), 16) & ~1L;
            Address entry = toAddr(number);
            currentProgram.getProgramContext().setValue(thumb, entry, entry.add(0x1000), BigInteger.ONE);
        }
        // Boundary-only declarations keep tail calls from absorbing unrelated
        // mixed ARM/Thumb RTOS veneers. Their implementations are NOT analysed
        // or claimed by these placeholders; all original bytes stay unchanged.
        long[] boundaries = controller ? new long[] {} : new long[] {0x1035c98cL, 0x1035d374L, 0x1035d1baL,
                             0x1035d1c0L, 0x1035d254L, 0x1035d2dcL, 0x1035d43aL,
                             0x1022d6e0L, // separately bounded frame-object release helper
                             0x1035d1e8L, 0x1035d1ecL}; // input-cache copy veneers; do not absorb RTOS/mixed-mode code
        AddressSet allowed = new AddressSet(currentProgram.getMemory());
        for (long number : boundaries) {
            Address entry = toAddr(number);
            // A placeholder alone does not stop recursive disassembly. Letting
            // it enter a mixed-mode RTOS veneer can turn the boundary into a
            // thunk and contaminate the caller with incorrectly decoded ARM.
            allowed.delete(entry, entry.add(1));
            if (getFunctionAt(entry) == null) {
                Function boundary = currentProgram.getFunctionManager().createFunction(
                    "boundary_" + Long.toHexString(number), entry, new AddressSet(entry, entry.add(1)),
                    SourceType.USER_DEFINED);
                boundary.setComment("Analysis boundary only; implementation not analysed here.");
            }
        }
        DecompInterface decompiler = new DecompInterface();
        DecompileOptions options = new DecompileOptions();
        options.setRespectReadOnly(true);
        decompiler.setOptions(options);
        decompiler.openProgram(currentProgram);
        try {
            for (int i = firstFunction; i < args.length; i++) {
                long number = Long.parseUnsignedLong(args[i].replace("0x", ""), 16) & ~1L;
                Address entry = toAddr(number);
                String hex = Long.toHexString(number);
                DisassembleCommand command = new DisassembleCommand(entry, allowed, true);
                if (!command.applyTo(currentProgram, monitor)) {
                    index.append(hex).append("\tmissing\tfalse\tDisassembly failed\n");
                    continue;
                }
                // With -noanalysis, the decompiler discovers TBB cases only
                // inside its private view, after our tail-call pass. Materialize
                // these six independently decoded C1.70 tables first. Verify
                // every byte; this is analysis metadata, never a ROM patch.
                long[] switches = {0x102390daL, 0x1023913aL, 0x102391d4L,
                                   0x1023927aL, 0x102392c8L, 0x10239320L};
                int[][] tables = {{2,36,13}, {2,65,13,46}, {2,36,13},
                                  {2,28,15}, {2,35,13}, {27,27,27,27,3}};
                for (int j = 0; j < switches.length; j++) {
                    Instruction jump = getInstructionAt(toAddr(switches[j]));
                    if (jump == null || !jump.getMnemonicString().equalsIgnoreCase("tbb")) continue;
                    Address table = jump.getAddress().add(4);
                    for (int k = 0; k < tables[j].length; k++) {
                        if ((getByte(table.add(k)) & 255) != tables[j][k]) {
                            throw new IllegalStateException("C1.70 TBB table mismatch");
                        }
                        Address target = table.add(2 * tables[j][k]);
                        jump.addMnemonicReference(target, RefType.COMPUTED_JUMP, SourceType.USER_DEFINED);
                        new DisassembleCommand(target, allowed, true).applyTo(currentProgram, monitor);
                    }
                }
                InstructionIterator instructions = currentProgram.getListing().getInstructions(true);
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    if (!instruction.getFlowType().isJump() || instruction.getFlowType().isConditional()) continue;
                    Address[] targets = instruction.getFlows();
                    if (targets.length != 1) continue;
                    for (long boundary : boundaries) {
                        if (targets[0].getOffset() == boundary) {
                            instruction.setFlowOverride(FlowOverride.CALL_RETURN);
                        }
                    }
                }
                Function function = getFunctionAt(entry);
                if (function == null) {
                    function = createFunction(entry, "z62_" + hex);
                }
                if (function == null || !function.getEntryPoint().equals(entry)) {
                    index.append(hex).append("\tmissing\tfalse\tFunction creation failed\n");
                    continue;
                }
                StringBuilder listing = new StringBuilder();
                InstructionIterator body = currentProgram.getListing().getInstructions(function.getBody(), true);
                while (body.hasNext()) {
                    Instruction instruction = body.next();
                    listing.append(instruction.getAddress()).append(": ").append(instruction)
                        .append(" ; ").append(instruction.getFlowType()).append('\n');
                }
                Files.writeString(output.resolve(hex + ".asm"), listing.toString(), StandardOpenOption.CREATE_NEW);
                decompiler.flushCache();
                DecompileResults result = decompiler.decompileFunction(function, 60, monitor);
                boolean complete = result.decompileCompleted() && result.getDecompiledFunction() != null;
                String message = result.getErrorMessage();
                if (message == null) message = "";
                index.append(hex).append('\t').append(function.getName()).append('\t')
                    .append(complete).append('\t').append(message.replace('\n', ' ').replace('\t', ' ')).append('\n');
                if (complete) {
                    String text = "/* Ghidra 11.4.2; original Z62 C1.70; base " + Long.toHexString(baseNumber) + "; Thumb.\n" +
                        " * Scoped decompilation; validate against instruction and runtime evidence.\n" +
                        " * Message: " + message.replace("*/", "* /") + "\n */\n" +
                        result.getDecompiledFunction().getC();
                    Files.writeString(output.resolve(hex + ".c"), text, StandardOpenOption.CREATE_NEW);
                }
                println("Z62_DECOMPILE " + hex + " complete=" + complete);
            }
        } finally {
            decompiler.dispose();
        }
        Files.writeString(output.resolve("functions.tsv"), index.toString(), StandardOpenOption.CREATE_NEW);
        Files.writeString(output.resolve("program.txt"),
            "language=" + currentProgram.getLanguageID() + "\nbase=" + currentProgram.getImageBase() +
            "\nformat=raw firmware module; no PE/ELF import table\n" +
            "mmio=" + (controller ? "40000000/30000,50060000/1000,e000e000/2000" :
            "20068000/4000,20100000/10000,20380000/10000,203c0000/10000") + "; volatile analysis metadata\n" +
            "analysis=selected functions only; original input bytes not modified\n",
            StandardOpenOption.CREATE_NEW);
    }
}
