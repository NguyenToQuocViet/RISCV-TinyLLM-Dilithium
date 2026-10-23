#------------------------------------------------------------------------------
# Module      : request_formatter_cocotb
# Description : Directed checks for request address, byte enables and write data.
# Author      : Viet Nguyen To Quoc, Codex
# Date        : 2026-10-23
#------------------------------------------------------------------------------

import cocotb
from cocotb.triggers import Timer

async def direct_check(
    dut,
    effective_address,
    store_data,
    mem_type,
    expected_address,
    expected_data,
    expected_be,
):
    dut.effective_address.value = effective_address
    dut.store_data.value        = store_data
    dut.mem_type.value          = mem_type

    await Timer(1, unit="ns")

    aligned_address = int(dut.aligned_address.value)
    write_data      = int(dut.write_data.value)
    byte_enable     = int(dut.byte_enable.value)

    assert aligned_address == expected_address, (
        f"Address: Expected 0x{expected_address:08X}, Got 0x{aligned_address:08X}"
    )

    assert byte_enable == expected_be, (
        f"Byte enable: Expected {expected_be:04b}, Got {byte_enable:04b}"
    )

    assert write_data == expected_data, (
        f"Write data: Expected 0x{expected_data:08X}, Got 0x{write_data:08X}"
    )

@cocotb.test()
async def test_byte_formatting(dut):
    # BYTE -> mem_type=0
    #test choosing byte enable
    await direct_check(
        dut,
        effective_address=0x19A7_42C0,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0x19A7_42C0,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0xE035_6B95,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0xE035_6B94,
        expected_be=0b0010,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0x724C_DA3A,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0x724C_DA38,
        expected_be=0b0100,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0xA86F_103F,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0xA86F_103C,
        expected_be=0b1000,
        expected_data=0xEFEF_EFEF,
    )

    #test address + 4
    await direct_check(
        dut,
        effective_address=0x19A7_42C4,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0x19A7_42C4,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    #test data=0
    await direct_check(
        dut,
        effective_address=0x3D92_71A4,
        store_data=0x0000_0000,
        mem_type=0,
        expected_address=0x3D92_71A4,
        expected_be=0b0001,
        expected_data=0x0000_0000,
    )

    #test data=F
    await direct_check(
        dut,
        effective_address=0xC407_EB18,
        store_data=0xFFFF_FFFF,
        mem_type=0,
        expected_address=0xC407_EB18,
        expected_be=0b0001,
        expected_data=0xFFFF_FFFF,
    )

    #test boundary address 0
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0x0000_0000,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    #test last word address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFC,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    #test last byte address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFF,
        store_data=0xDEAD_BEEF,
        mem_type=0,
        expected_address=0xFFFF_FFFC,
        expected_be=0b1000,
        expected_data=0xEFEF_EFEF,
    )

    #test upper data bits do not affect byte replication
    await direct_check(
        dut,
        effective_address=0x6AF0_932C,
        store_data=0x1234_56EF,
        mem_type=0,
        expected_address=0x6AF0_932C,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0x91B5_0C70,
        store_data=0x0000_00EF,
        mem_type=0,
        expected_address=0x91B5_0C70,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )


@cocotb.test()
async def test_halfword_formatting(dut):
    # HALF -> mem_type=1
    #test choosing lower halfword
    await direct_check(
        dut,
        effective_address=0x58E3_A6D0,
        store_data=0xDEAD_BEEF,
        mem_type=1,
        expected_address=0x58E3_A6D0,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test choosing upper halfword
    await direct_check(
        dut,
        effective_address=0xB249_187A,
        store_data=0xDEAD_BEEF,
        mem_type=1,
        expected_address=0xB249_1878,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )

    #test address + 4
    await direct_check(
        dut,
        effective_address=0x58E3_A6D4,
        store_data=0xDEAD_BEEF,
        mem_type=1,
        expected_address=0x58E3_A6D4,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test data=0
    await direct_check(
        dut,
        effective_address=0x07DC_F524,
        store_data=0x0000_0000,
        mem_type=1,
        expected_address=0x07DC_F524,
        expected_be=0b0011,
        expected_data=0x0000_0000,
    )

    #test data=F
    await direct_check(
        dut,
        effective_address=0xF631_8BCE,
        store_data=0xFFFF_FFFF,
        mem_type=1,
        expected_address=0xF631_8BCC,
        expected_be=0b1100,
        expected_data=0xFFFF_FFFF,
    )

    #test boundary address 0
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=1,
        expected_address=0x0000_0000,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test last word address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFC,
        store_data=0xDEAD_BEEF,
        mem_type=1,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test last aligned halfword address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFE,
        store_data=0xDEAD_BEEF,
        mem_type=1,
        expected_address=0xFFFF_FFFC,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )

    #test upper data bits do not affect halfword replication
    await direct_check(
        dut,
        effective_address=0x2CA8_D152,
        store_data=0x1234_BEEF,
        mem_type=1,
        expected_address=0x2CA8_D150,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )

    await direct_check(
        dut,
        effective_address=0xD785_406E,
        store_data=0x0000_BEEF,
        mem_type=1,
        expected_address=0xD785_406C,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )


@cocotb.test()
async def test_word_formatting(dut):
    # WORD -> mem_type=2
    #test full word data and byte enable
    await direct_check(
        dut,
        effective_address=0x83BE_9728,
        store_data=0xDEAD_BEEF,
        mem_type=2,
        expected_address=0x83BE_9728,
        expected_be=0b1111,
        expected_data=0xDEAD_BEEF,
    )

    #test address + 4
    await direct_check(
        dut,
        effective_address=0x83BE_972C,
        store_data=0x1234_5678,
        mem_type=2,
        expected_address=0x83BE_972C,
        expected_be=0b1111,
        expected_data=0x1234_5678,
    )

    #test data=0
    await direct_check(
        dut,
        effective_address=0x4F10_CAE4,
        store_data=0x0000_0000,
        mem_type=2,
        expected_address=0x4F10_CAE4,
        expected_be=0b1111,
        expected_data=0x0000_0000,
    )

    #test data=F
    await direct_check(
        dut,
        effective_address=0x613A_85D8,
        store_data=0xFFFF_FFFF,
        mem_type=2,
        expected_address=0x613A_85D8,
        expected_be=0b1111,
        expected_data=0xFFFF_FFFF,
    )

    #test data below bit 31 boundary
    await direct_check(
        dut,
        effective_address=0xAC72_8B40,
        store_data=0x7FFF_FFFF,
        mem_type=2,
        expected_address=0xAC72_8B40,
        expected_be=0b1111,
        expected_data=0x7FFF_FFFF,
    )

    #test data with only bit 31 set
    await direct_check(
        dut,
        effective_address=0x35E9_F164,
        store_data=0x8000_0000,
        mem_type=2,
        expected_address=0x35E9_F164,
        expected_be=0b1111,
        expected_data=0x8000_0000,
    )

    #test boundary address 0
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=2,
        expected_address=0x0000_0000,
        expected_be=0b1111,
        expected_data=0xDEAD_BEEF,
    )

    #test last aligned word address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFC,
        store_data=0x1234_5678,
        mem_type=2,
        expected_address=0xFFFF_FFFC,
        expected_be=0b1111,
        expected_data=0x1234_5678,
    )


@cocotb.test()
async def test_unsigned_byte_formatting(dut):
    # BYTE_U -> mem_type=4; same directed vectors as MEM_BYTE
    #test choosing byte enable
    await direct_check(
        dut,
        effective_address=0x19A7_42C0,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0x19A7_42C0,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0xE035_6B95,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0xE035_6B94,
        expected_be=0b0010,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0x724C_DA3A,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0x724C_DA38,
        expected_be=0b0100,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0xA86F_103F,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0xA86F_103C,
        expected_be=0b1000,
        expected_data=0xEFEF_EFEF,
    )

    #test address + 4
    await direct_check(
        dut,
        effective_address=0x19A7_42C4,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0x19A7_42C4,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    #test data=0
    await direct_check(
        dut,
        effective_address=0x3D92_71A4,
        store_data=0x0000_0000,
        mem_type=4,
        expected_address=0x3D92_71A4,
        expected_be=0b0001,
        expected_data=0x0000_0000,
    )

    #test data=F
    await direct_check(
        dut,
        effective_address=0xC407_EB18,
        store_data=0xFFFF_FFFF,
        mem_type=4,
        expected_address=0xC407_EB18,
        expected_be=0b0001,
        expected_data=0xFFFF_FFFF,
    )

    #test boundary address 0
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0x0000_0000,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    #test last word address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFC,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    #test last byte address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFF,
        store_data=0xDEAD_BEEF,
        mem_type=4,
        expected_address=0xFFFF_FFFC,
        expected_be=0b1000,
        expected_data=0xEFEF_EFEF,
    )

    #test upper data bits do not affect byte replication
    await direct_check(
        dut,
        effective_address=0x6AF0_932C,
        store_data=0x1234_56EF,
        mem_type=4,
        expected_address=0x6AF0_932C,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )

    await direct_check(
        dut,
        effective_address=0x91B5_0C70,
        store_data=0x0000_00EF,
        mem_type=4,
        expected_address=0x91B5_0C70,
        expected_be=0b0001,
        expected_data=0xEFEF_EFEF,
    )


@cocotb.test()
async def test_unsigned_halfword_formatting(dut):
    # HALF_U -> mem_type=5; same directed vectors as MEM_HALF
    #test choosing lower halfword
    await direct_check(
        dut,
        effective_address=0x58E3_A6D0,
        store_data=0xDEAD_BEEF,
        mem_type=5,
        expected_address=0x58E3_A6D0,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test choosing upper halfword
    await direct_check(
        dut,
        effective_address=0xB249_187A,
        store_data=0xDEAD_BEEF,
        mem_type=5,
        expected_address=0xB249_1878,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )

    #test address + 4
    await direct_check(
        dut,
        effective_address=0x58E3_A6D4,
        store_data=0xDEAD_BEEF,
        mem_type=5,
        expected_address=0x58E3_A6D4,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test data=0
    await direct_check(
        dut,
        effective_address=0x07DC_F524,
        store_data=0x0000_0000,
        mem_type=5,
        expected_address=0x07DC_F524,
        expected_be=0b0011,
        expected_data=0x0000_0000,
    )

    #test data=F
    await direct_check(
        dut,
        effective_address=0xF631_8BCE,
        store_data=0xFFFF_FFFF,
        mem_type=5,
        expected_address=0xF631_8BCC,
        expected_be=0b1100,
        expected_data=0xFFFF_FFFF,
    )

    #test boundary address 0
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=5,
        expected_address=0x0000_0000,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test last word address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFC,
        store_data=0xDEAD_BEEF,
        mem_type=5,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0011,
        expected_data=0xBEEF_BEEF,
    )

    #test last aligned halfword address
    await direct_check(
        dut,
        effective_address=0xFFFF_FFFE,
        store_data=0xDEAD_BEEF,
        mem_type=5,
        expected_address=0xFFFF_FFFC,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )

    #test upper data bits do not affect halfword replication
    await direct_check(
        dut,
        effective_address=0x2CA8_D152,
        store_data=0x1234_BEEF,
        mem_type=5,
        expected_address=0x2CA8_D150,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )

    await direct_check(
        dut,
        effective_address=0xD785_406E,
        store_data=0x0000_BEEF,
        mem_type=5,
        expected_address=0xD785_406C,
        expected_be=0b1100,
        expected_data=0xBEEF_BEEF,
    )


@cocotb.test()
async def test_reserved_mem_type(dut):
    #test reserved code 011 at all four offsets
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=0b011,
        expected_address=0x0000_0000,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0x9E4B_7C21,
        store_data=0xFFFF_FFFF,
        mem_type=0b011,
        expected_address=0x9E4B_7C20,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0x8000_0002,
        store_data=0x1234_5678,
        mem_type=0b011,
        expected_address=0x8000_0000,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0xFFFF_FFFF,
        store_data=0xA5A5_5A5A,
        mem_type=0b011,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    #test reserved code 110 at all four offsets
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=0b110,
        expected_address=0x0000_0000,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0x2D85_A639,
        store_data=0xFFFF_FFFF,
        mem_type=0b110,
        expected_address=0x2D85_A638,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0x8000_0002,
        store_data=0x1234_5678,
        mem_type=0b110,
        expected_address=0x8000_0000,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0xFFFF_FFFF,
        store_data=0xA5A5_5A5A,
        mem_type=0b110,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    #test reserved code 111 at all four offsets
    await direct_check(
        dut,
        effective_address=0x0000_0000,
        store_data=0xDEAD_BEEF,
        mem_type=0b111,
        expected_address=0x0000_0000,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0xC713_E4AD,
        store_data=0xFFFF_FFFF,
        mem_type=0b111,
        expected_address=0xC713_E4AC,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0x8000_0002,
        store_data=0x1234_5678,
        mem_type=0b111,
        expected_address=0x8000_0000,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )

    await direct_check(
        dut,
        effective_address=0xFFFF_FFFF,
        store_data=0xA5A5_5A5A,
        mem_type=0b111,
        expected_address=0xFFFF_FFFC,
        expected_be=0b0000,
        expected_data=0x0000_0000,
    )
