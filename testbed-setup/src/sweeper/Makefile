# set compiler here
ifeq ($(ARCH), armv7l)
	CC := arm-openwrt-linux-muslgnueabi-gcc
	CFLAGS := -O2 -Wall -Wno-comment -std=c11 -static
	# LD := arm-openwrt-linux-muslgnueabi-ld
	INC := -I ~/workbench/lede-ad7200/staging_dir/target-arm_cortex-a15+neon-vfpv4_musl-1.1.16_eabi/usr/include ~/workbench/lede-ad7200/staging_dir/target-arm_cortex-a15+neon-vfpv4_musl-1.1.16_eabi/usr/lib
else
	CC := gcc
	CFLAGS := -g -ggdb -gdwarf-2 -O2 -Wall -Wno-comment -std=c11 -static
	INC := -Iinclude
endif

# directories
SRCDIR := .
BUILDDIR := build
TARGET := sweeper

SRCEXT := c
SOURCES := $(shell find $(SRCDIR) -type f -name *.$(SRCEXT))
OBJECTS := $(patsubst $(SRCDIR)/%,$(BUILDDIR)/%,$(SOURCES:.$(SRCEXT)=.o))

#all: $(TARGET) $(TARGET)
all: $(TARGET)
	@echo " Doing nothing..."

$(TARGET): $(OBJECTS)
	@echo " Linking..."
	@echo " $(CC) $^ -o $(TARGET) $(LIB)"; $(CC) $^ -o $(TARGET) $(LIB)

$(BUILDDIR)/%.o: $(SRCDIR)/%.$(SRCEXT)
	@mkdir -p $(BUILDDIR)
	@echo " $(CC) $(CFLAGS) $(INC) -c -o $@ $<"; $(CC) $(CFLAGS) $(INC) -c -o $@ $<

clean:
	@echo " Cleaning..."; 
	$(RM) -r $(BUILDDIR) $(TARGET) *~

.PHONY: clean
